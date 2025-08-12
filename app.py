# app.py
import webbrowser
from flask import Flask, render_template, request, send_from_directory, flash, redirect, url_for, get_flashed_messages
import csv
import os
from datetime import datetime
from escpos import printer
from werkzeug.utils import secure_filename
import json
from threading import Timer

# --- Load Cost Configuration ---
try:
    with open('costs.json', 'r') as f:
        COSTS = json.load(f)
    FDM_COSTS = COSTS.get('FDM_COSTS', {})
    RESIN_COST_PER_ML = COSTS.get('RESIN_COST_PER_ML', 0.30)
    # Add MATERIAL_TYPES to be passed to the template
    MATERIAL_TYPES = COSTS.get('MATERIAL_TYPES', {})
except FileNotFoundError:
    print("Warning: costs.json not found. Using default costs.")
    FDM_COSTS = {'PLA': 0.08, 'PLA+': 0.08, 'PETG': 0.08, 'TPU': 0.10}
    RESIN_COST_PER_ML = 0.30
    MATERIAL_TYPES = {}

# Initialize the Flask application
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_super_secret_key_change_me'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'gcode', 'bgcode', 'stl'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Printer Initialization ---

try:
    p = printer.Serial('COM2')
except Exception as e:
    p = None
    print(f"Could not initialize printer: {e}")
# p = None # Set printer to None to disable printing

# Create the 'uploads' directory if it doesn't already exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    """Checks if the uploaded file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def print_store_receipt(p, data):
    """Formats and prints a store-style receipt for either FDM or Resin prints."""
    if p is None:
        print("Printer not available. Skipping print.")
        flash('Data saved, but printer is not connected.', 'error')
        return

    try:
        # --- Universal Header ---
        p.set(align='center', font='a', bold=True, width=2, height=2)
        p.text("3D Print Job\n")
        p.set(align='center', font='b', bold=False, width=1, height=1)
        p.text("----------------------------------------\n")

        # --- Job Details ---
        p.set(align='left', font='b')
        job_id = data['timestamp'].replace('-', '').replace(':', '').replace(' ', '')
        date_str = datetime.strptime(data['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%m/%d/%Y %I:%M %p')
        p.text(f"Job ID: {job_id}\n")
        p.text(f"Date: {date_str}\n")
        p.text(f"Operator: {data.get('user_name', 'N/A')}\n")
        p.text(f"Email: {data.get('user_email', 'N/A')}\n")
        p.text(f"Print Type: {data.get('print_type', 'N/A')}\n")
        p.set(align='center', font='b', bold=False, width=1, height=1)
        p.text("----------------------------------------\n\n")

        # --- Print Specific Details ---
        p.set(align='left', font='a', bold=True)
        p.text("Print Details\n")
        p.set(font='b', bold=False)

        unit = ''
        if data.get('print_type') == 'FDM':
            unit = 'g'
            material_display = data.get('other_filament_type') or data.get('filament_type')
            p.text(f"{'Filename:'.ljust(18)} {data.get('gcode_file', 'N/A')}\n")
            p.text(f"{'Printer Model:'.ljust(18)} {data.get('printer_model', 'N/A')}\n")
            p.text(f"{'Filament Brand:'.ljust(18)} {data.get('filament_brand', 'N/A')}\n")
            p.text(f"{'Filament Type:'.ljust(18)} {material_display}\n")
            p.text(f"{'Filament Color:'.ljust(18)} {data.get('filament_color', 'N/A')}\n")
            p.text(f"{'Filament Amount:'.ljust(18)} {data.get('filament_amount', 0)}{unit}\n")
            p.text(f"{'Filament Source:'.ljust(18)} {data.get('filament_source', 'N/A')}\n")
        elif data.get('print_type') == 'Resin':
            unit = 'ml'
            material_display = data.get('other_resin_type') or data.get('resin_type')
            p.text(f"{'Filename:'.ljust(18)} {data.get('gcode_file', 'N/A')}\n")
            p.text(f"{'Printer Model:'.ljust(18)} {data.get('printer_model', 'N/A')}\n")
            p.text(f"{'Resin Type:'.ljust(18)} {material_display}\n")
            p.text(f"{'Resin Amount:'.ljust(18)} {data.get('resin_amount', 0)}{unit}\n")
            p.text(f"{'Resin Source:'.ljust(18)} {data.get('resin_source', 'N/A')}\n")
        
        # --- Cost Section ---
        cost = data.get('cost', 0)
        if cost > 0:
            p.set(align='center', font='b')
            p.text("----------------------------------------\n")
            p.set(align='left', font='a', bold=True)
            p.text("Cost Breakdown\n")
            p.set(font='b', bold=False)
            cost_rate = data.get('cost_rate', 0)
            p.text(f"{'Cost per Unit:'.ljust(18)} ${cost_rate:.4f}/{unit}\n")
            p.text(f"{'Total Cost:'.ljust(18)} ${cost:.2f}\n")

        # --- Footer ---
        p.set(align='center', font='b')
        p.text("\n----------------------------------------\n")
        p.text("Thank you for using the lab!\n")
        if job_id:
            p.barcode(job_id[:12].replace(" ", ""), 'EAN13', 64, 2, '', '')
        p.cut()
        return True # Indicate success
    except Exception as e:
        print(f"Failed to print receipt: {e}")
        # Check if a flash message about printer connection already exists
        if not any(msg for cat, msg in get_flashed_messages(with_categories=True) if "printer" in msg):
            flash('Data saved, but there was an error connecting to the printer.', 'error')
        return False # Indicate failure

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print_type = request.form.get('print_type')
        
        data = {
            'timestamp': timestamp,
            'user_name': request.form.get('user_name'),
            'user_email': request.form.get('user_email'),
            'print_type': print_type,
            'gcode_file': 'N/A',
            'cost': 0.0,
            'cost_rate': 0.0
        }

        # --- File Handling ---
        if 'gcode_file' in request.files:
            file = request.files['gcode_file']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                data['gcode_file'] = filename

        # --- FDM Specific Data & Cost ---
        if print_type == 'FDM':
            filament_type = request.form.get('filament_type')
            filament_amount = float(request.form.get('filament_amount', 0))
            filament_source = request.form.get('filament_source')
            
            data.update({
                'printer_model': request.form.get('fdm_printer'),
                'filament_type': filament_type,
                'filament_brand': request.form.get('filament_brand'),
                'filament_color': request.form.get('filament_color'),
                'filament_amount': filament_amount,
                'filament_source': filament_source,
                'other_filament_type': request.form.get('other_filament_type') if filament_type == 'Other' else None,
            })

            if ((filament_type == 'Other') & (filament_source == 'Lab')):
                cost_rate = float(request.form.get('custom_cost_fdm', 0))
                data['cost_rate'] = cost_rate
                data['cost'] = filament_amount * cost_rate
            elif filament_source == 'Lab':
                cost_rate = FDM_COSTS.get(filament_type, 0)
                data['cost_rate'] = cost_rate
                data['cost'] = filament_amount * cost_rate

        # --- Resin Specific Data & Cost ---
        elif print_type == 'Resin':
            resin_type = request.form.get('resin_type')
            resin_amount = float(request.form.get('resin_amount', 0))
            resin_source = request.form.get('resin_source')

            data.update({
                'printer_model': request.form.get('resin_printer'),
                'resin_type': resin_type,
                'resin_amount': resin_amount,
                'resin_source': resin_source,
                'other_resin_type': request.form.get('other_resin_type') if resin_type == 'Other' else None
            })

            if ((resin_type == 'Other') & (resin_source == 'Lab')):
                cost_rate = float(request.form.get('custom_cost_resin', 0))
                data['cost_rate'] = cost_rate
                data['cost'] = resin_amount * cost_rate
            elif resin_source == 'Lab':
                cost_rate = RESIN_COST_PER_ML
                data['cost_rate'] = cost_rate
                data['cost'] = resin_amount * cost_rate

        # --- CSV Logging ---
        csv_file = 'receipts.csv'
        # More comprehensive fieldnames for better logging

        #combines data types for storage before writing to CSV
        if data.get('print_type') == 'FDM':
            data['material_type'] = data.get('other_filament_type') if data.get('filament_type') == 'Other' else data.get('filament_type')
            data['material_amount'] = data.get('filament_amount')
            data['material_source'] = data.get('filament_source')

        elif data.get('print_type') == 'Resin':
            data['material_type'] = data.get('other_resin_type') if data.get('resin_type') == 'Other' else data.get('resin_type')
            data['material_amount'] = data.get('resin_amount')
            data['material_source'] = data.get('resin_source')

        fieldnames = [
            'timestamp', 'user_name', 'user_email', 'print_type', 'gcode_file',
            'printer_model', 'material_type', 'material_amount', 'material_source', 'filament_brand',
            'filament_color','cost_rate', 'cost'
        ]

        # Ensure all keys in data exist in fieldnames for DictWriter
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

        return redirect(url_for('index'))

    # Combine all cost and material data into a single context dictionary
    context = {
        "FDM_COSTS": FDM_COSTS,
        "RESIN_COST_PER_ML": RESIN_COST_PER_ML,
        "MATERIAL_TYPES": MATERIAL_TYPES
    }
    return render_template('index.html', costs=context)

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
        # Reconstruct the data dictionary for the print_store_receipt function
        data = {
            'timestamp': receipt_data['timestamp'],
            'user_name': receipt_data['user_name'],
            'user_email': receipt_data['user_email'],
            'print_type': receipt_data['print_type'],
            'gcode_file': receipt_data['gcode_file'],
            'printer_model': receipt_data['printer_model'],
            'cost': float(receipt_data.get('cost', 0)),
            'cost_rate': float(receipt_data.get('cost_rate', 0))
        }
        
        print_type = receipt_data['print_type']
        material_type = receipt_data['material_type']
        material_amount = float(receipt_data.get('material_amount', 0))
        
        if print_type == 'FDM':
            data.update({
                'filament_amount': material_amount,
                'filament_source': receipt_data.get('material_source'),
                'filament_brand': receipt_data.get('filament_brand'),
                'filament_color': receipt_data.get('filament_color')
            })
            # Determine if it was an 'Other' type
            if material_type not in FDM_COSTS:
                data['filament_type'] = 'Other'
                data['other_filament_type'] = material_type
            else:
                data['filament_type'] = material_type
        
        elif print_type == 'Resin':
            data.update({
                'resin_amount': material_amount,
                'resin_source': receipt_data.get('material_source')
            })
            # Determine if it was an 'Other' type by checking against known resin types
            known_resin_types = [item for sublist in MATERIAL_TYPES.values() for item in sublist]
            if material_type not in known_resin_types:
                data['resin_type'] = 'Other'
                data['other_resin_type'] = material_type
            else:
                data['resin_type'] = material_type

        if print_store_receipt(p, data):
            flash(f"Receipt for job {job_id} sent to printer.", "success")
        else:
            flash(f"Could not reprint receipt for job {job_id}. Check printer connection.", "error")

    else:
        flash(f"Job with ID {job_id} not found.", "error")

    return redirect(url_for('receipts'))

@app.route('/receipts')
def receipts():
    """Displays all submitted receipts from the CSV file."""
    header = []
    rows = []
    try:
        with open('receipts.csv', 'r', newline='') as f:
            reader = csv.DictReader(f)
            # Check if there are any rows
            try:
                sample_row = next(reader)
            except StopIteration:
                sample_row = None

            if sample_row:
                # Get header from the first row, excluding empty columns
                header = [h for h in reader.fieldnames if sample_row.get(h)]
                # The reader iterator is now at the second row.
                # We combine our saved first row with the rest of the rows.
                all_rows = [sample_row] + list(reader)
            else:
                all_rows = []


            for row in all_rows:
                # Format cost
                if row.get('cost') and row['cost']:
                    try:
                        row['cost'] = f"${float(row['cost']):.2f}"
                    except (ValueError, TypeError):
                        row['cost'] = '$0.00'
                # Create download link for file
                if row.get('gcode_file') and row['gcode_file'] != 'N/A':
                    filename = row['gcode_file']
                    row['gcode_file'] = {'text': filename, 'url': url_for('uploaded_file', filename=filename)}
                rows.append(row)

    except FileNotFoundError:
        flash("No receipts have been logged yet.", "info")
    except Exception as e:
        print(f"Error reading CSV: {e}")
        flash("Error reading the receipts file.", "error")

    return render_template('receipts.html', header=header, rows=rows)


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serves uploaded files from the 'uploads' directory for download."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- Function to open the browser ---
def open_browser():
      webbrowser.open_new('http://127.0.0.1:5000/')

if __name__ == '__main__':
    # starts the server and opens the browser after a short delay
    Timer(1, open_browser).start()
    app.run(host='127.0.0.1', port=5000, debug=False)