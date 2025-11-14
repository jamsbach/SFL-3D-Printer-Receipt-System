# app.py
from flask import Flask, render_template, request, flash, redirect, url_for, get_flashed_messages, abort, session
import csv
import os
import json
import webbrowser
from datetime import datetime
from escpos import printer
from threading import Timer

# --- Load Configuration ---
CONFIG_FILE_PATH = 'config.json'
try:
    with open(CONFIG_FILE_PATH, 'r') as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    print(f"FATAL ERROR: {CONFIG_FILE_PATH} not found. Application cannot start.")
    exit()
except json.JSONDecodeError:
    print(f"FATAL ERROR: {CONFIG_FILE_PATH} is not valid JSON. Application cannot start.")
    exit()

# --- Admin Password ---
ADMIN_PASSWORD = 'adminSFL'


# Initialize the Flask application
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_super_secret_key_change_me'

# --- Printer Initialization ---
try:
    p = printer.Serial('COM2')
except Exception as e:
    p = None
    print(f"Could not initialize printer: {e}")
# p = None # Set printer to None to disable printing

def print_store_receipt(p, data):
    """Formats and prints a store-style receipt for any job type."""
    if p is None:
        print("Printer not available. Skipping print.")
        flash('Data saved, but printer is not connected.', 'error')
        return

    try:
        # --- Universal Header ---
        p.set(align='center', font='a', bold=True, width=2, height=2)
        p.text("SFL Job Receipt\n")
        p.set(align='center', font='b', bold=False, width=1, height=1)
        p.text("----------------------------------------\n")

        # --- Job Details ---
        p.set(align='left', font='b')
        job_id = data['timestamp'].replace('-', '').replace(':', '').replace(' ', '')
        date_str = datetime.strptime(data['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%m/%d/%Y %I:%M %p')
        
        p.text(f"Job ID: {job_id}\n")
        p.text(f"Date: {date_str}\n")
        
        # Handle User/Email vs. Group Name
        user_name = data.get('user_name', 'N/A')
        group_name = data.get('group_name', 'N/A')
        email = data.get('email', 'N/A')
        
        # Always show user name
        p.text(f"Operator: {user_name}\n")
        if email and email != 'N/A':
            p.text(f"Email: {email}\n")
        
        # Show group name if it exists
        if data.get('source') in ['Club', 'Class', 'Lab'] and group_name != 'N/A':
             p.text(f"Group: {group_name} ({data.get('source')})\n")
        else:
             p.text(f"Source: {data.get('source', 'N/A')}\n")
             
        p.text(f"Machine: {data.get('machine_name', 'N/A')}\n")
        
        # Add Specific Machine if it exists
        specific_machine = data.get('specific_machine', 'N/A')
        if specific_machine and specific_machine != 'N/OS':
            p.text(f"Unit: {specific_machine}\n")

        # --- NEW: Add Filament Brand/Color ---
        brand = data.get('filament_brand')
        color = data.get('filament_color')
        
        if brand and brand != 'N/A':
            p.text(f"Filament Brand: {brand}\n")
        if color and color != 'N/A':
            p.text(f"Filament Color: {color}\n")
        # --- END NEW ---

        p.set(align='center', font='b', bold=False, width=1, height=1)
        p.text("----------------------------------------\n\n")

        # --- Print Specific Details ---
        p.set(align='left', font='a', bold=True)
        p.text("Job Details\n")
        p.set(font='b', bold=False)
        
        unit = data.get('unit_suffix', '')
        p.text(f"{'Material:'.ljust(18)} {data.get('material_type', 'N/A')}\n")
        p.text(f"{'Amount:'.ljust(18)} {data.get('material_amount', 0)} {unit}\n")

        # --- Cost Section ---
        cost = float(data.get('cost', 0))
        if cost > 0:
            p.set(align='center', font='b')
            p.text("----------------------------------------\n")
            p.set(align='left', font='a', bold=True)
            p.text("Cost Breakdown\n")
            p.set(font='b', bold=False)
            cost_rate = float(data.get('cost_rate', 0))
            p.text(f"{'Cost per Unit:'.ljust(18)} ${cost_rate:.4f}/{unit}\n")
            p.text(f"{'Total Cost:'.ljust(18)} ${cost:.2f}\n")

        # --- Footer ---
        p.set(align='center', font='b')
        p.text("\n----------------------------------------\n")
        p.text("Thank you for using the SFL!\n")
        if job_id:
            p.barcode(job_id[:12].replace(" ", ""), 'EAN13', 64, 2, '', '')
        p.cut()
        return True # Indicate success
    except Exception as e:
        print(f"Failed to print receipt: {e}")
        if not any(msg for cat, msg in get_flashed_messages(with_categories=True) if "printer" in msg):
            flash('Data saved, but there was an error connecting to the printer.', 'error')
        return False # Indicate failure

@app.route('/')
def index():
    """Displays the main page with a list of available machines."""
    machines = {}
    for machine_id, details in CONFIG.items():
        machines[machine_id] = details.get('display_name', machine_id)
    return render_template('index.html', machines=machines)

@app.route('/job/<machine_id>', methods=['GET', 'POST'])
def job_form(machine_id):
    """Renders a dynamic form based on the machine_id from config.json."""
    if machine_id not in CONFIG:
        abort(404)
        
    machine_config = CONFIG[machine_id]
    
    if request.method == 'POST':
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        source = request.form.get('source')
        material_type = request.form.get('material_type')
        material_amount = float(request.form.get('material_amount', 0))
        
        data = {
            'timestamp': timestamp,
            'user_name': request.form.get('user_name', 'N/A'), # Always get user_name
            'email': request.form.get('email', 'N/A'),       # Always get email
            'group_name': 'N/A',
            'source': source,
            'machine_id': machine_id,
            'machine_name': machine_config.get('display_name', machine_id),
            'specific_machine': request.form.get('specific_machine', 'N/A'), # Get specific machine
            'material_type': material_type,
            'material_amount': material_amount,
            'unit_suffix': machine_config.get('unit_suffix', ''),
            'cost': 0.0,
            'cost_rate': 0.0,
            # --- NEW FIELDS ---
            'filament_brand': request.form.get('filament_brand', 'N/A'),
            'filament_color': request.form.get('filament_color', 'N/A'),
        }
        
        # Handle Group Name
        if source in ['Club', 'Class', 'Lab']:
            data['group_name'] = request.form.get('group_name', 'N/A')
            
        # Handle "Other" material name
        if material_type == 'Other':
            data['material_type'] = request.form.get('other_material_name', 'Other')

        # --- Cost Calculation ---
        cost_rate = 0.0
        selected_material_config = next((m for m in machine_config.get('materials', []) if m['name'] == material_type), None)
        
        if source == 'SFL':
            if selected_material_config:
                if selected_material_config.get('custom_cost', False):
                    cost_rate = float(request.form.get('custom_cost', 0))
                else:
                    cost_rate = selected_material_config.get('cost_per_unit', 0)
            
            data['cost_rate'] = cost_rate
            data['cost'] = material_amount * cost_rate

        # --- CSV Logging ---
        csv_file = 'receipts.csv'
        fieldnames = [
            'timestamp', 'user_name', 'email', 'group_name', 'source', 'machine_id', 'machine_name', 
            'specific_machine', 
            # --- NEW FIELDS FOR CSV ---
            'filament_brand', 'filament_color', 
            # --- END NEW FIELDS ---
            'material_type', 'material_amount', 'unit_suffix', 'cost_rate', 'cost'
        ]
        
        row_data = {key: data.get(key) for key in fieldnames}
        
        file_exists = os.path.isfile(csv_file)
        with open(csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists or f.tell() == 0:
                writer.writeheader()
            writer.writerow(row_data)

        # --- Receipt Printing ---
        printed_ok = print_store_receipt(p, data)
        if printed_ok:
            flash('Job logged and receipt printed successfully!', 'success')
        
        return redirect(url_for('job_form', machine_id=machine_id))
    
    # --- For GET request ---
    materials = {}
    for mat in machine_config.get('materials', []):
        materials[mat['name']] = mat.get('cost_per_unit', 0)
        
    return render_template('job_form.html', 
                           machine_id=machine_id, 
                           machine=machine_config, 
                           materials=json.dumps(materials))

@app.route('/receipts')
def receipts():
    """Displays all submitted receipts from the CSV file."""
    rows = []
    header = []
    try:
        with open('receipts.csv', 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames if reader.fieldnames else []
            for row in reader:
                rows.append(row)
                
    except FileNotFoundError:
        flash("No receipts have been logged yet.", "info")
    except Exception as e:
        print(f"Error reading CSV: {e}")
        flash("Error reading the receipts file.", "error")

    rows.reverse() # Show newest first
    
    # Define which columns to show in the table
    display_header = [
        'timestamp', 'machine_name', 'specific_machine', 'user_name', 'email', 'group_name', 'source', 
        'material_type', 'material_amount', 'cost', 'actions'
    ]
    
    filtered_header = [h for h in display_header if h in header or h == 'actions']
    return render_template('receipts.html', header=filtered_header, rows=rows)

@app.route('/reprint/<job_id>')
def reprint_receipt(job_id):
    """Finds a receipt by its timestamp (job_id) and reprints it."""
    csv_file = 'receipts.csv'
    receipt_data = None
    try:
        with open(csv_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['timestamp'] == job_id:
                    receipt_data = row
                    break
    except FileNotFoundError:
        flash("Receipts file not found.", "error")
        return redirect(url_for('receipts'))

    if receipt_data:
        # Convert types from CSV strings back to numbers
        receipt_data['cost'] = float(receipt_data.get('cost', 0))
        receipt_data['cost_rate'] = float(receipt_data.get('cost_rate', 0))
        receipt_data['material_amount'] = float(receipt_data.get('material_amount', 0))
        
        if print_store_receipt(p, receipt_data):
            flash(f"Receipt for job {job_id} sent to printer.", "success")
        else:
            flash(f"Could not reprint receipt for job {job_id}. Check printer connection.", "error")
    else:
        flash(f"Job with ID {job_id} not found.", "error")

    return redirect(url_for('receipts'))

# --- NEW ADMIN ROUTES ---

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Shows login page and handles login."""
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('Logged in successfully!', 'success')
            return redirect(url_for('admin_editor'))
        else:
            flash('Incorrect password.', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    """Logs the admin out by clearing the session."""
    session.pop('logged_in', None)
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))

@app.route('/admin/editor', methods=['GET', 'POST'])
def admin_editor():
    """Shows the config editor; handles saving the config."""
    # Check if user is logged in
    if not session.get('logged_in'):
        flash('You must be logged in to access this page.', 'error')
        return redirect(url_for('admin_login'))
    
    config_content = ""
    if request.method == 'POST':
        config_content = request.form.get('config_content')
        try:
            # Step 1: Validate the JSON
            new_config = json.loads(config_content)
            
            # Step 2: Write the (pretty-formatted) JSON back to the file
            with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(new_config, f, indent=4)
                
            flash('Config saved successfully! The application is restarting...', 'success')
            # The app will auto-restart here due to the 'extra_files' watch
            
        except json.JSONDecodeError as e:
            # If JSON is invalid, flash an error and show the editor with their bad content
            flash(f'Invalid JSON: {e}. Please correct the errors and try again.', 'error')
        except Exception as e:
            flash(f'An error occurred while saving: {e}', 'error')
            
    else:
        # GET Request: Read the current config file
        try:
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                config_content = f.read()
        except Exception as e:
            flash(f'Could not load config.json: {e}', 'error')
            
    return render_template('admin_editor.html', config_content=config_content)

# --- END NEW ADMIN ROUTES ---
# --- Function to open the browser ---
def open_browser():
      webbrowser.open_new('http://127.0.0.1:5000/')


# ... (rest of your app.py code) ...

if __name__ == '__main__':
    print("--- SFL Job Logger ---")
    print(f"Watching for changes in: {CONFIG_FILE_PATH}")
    print("Running at: http://127.0.0.1:5000/")
    
    # Check if this is the main process (not the reloader's child process)
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        Timer(1, open_browser).start()
        
    # Add extra_files=[CONFIG_FILE_PATH] to watch the config file for changes
    app.run(host='127.0.0.1', port=5000, debug=True, extra_files=[CONFIG_FILE_PATH])