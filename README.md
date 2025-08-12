This is a Flask system outputting to an ESC/POS controlled Epson TM-T20III Thermal Printer.
All user data is saved to a .csv file and optionally .gcode/.bgcode/.stl files can be uploaded to the "Uploads" folder upon submission.

Upon first running the app.py file both the uploads folder and "receipts.csv" files will be created.

```
pip install flask
pip install python-escpos
pip install werkzeug

pip install pyinstaller
```

To build the python app using pyinstaller run this command, make sure to include the proper directory to you esc/pos capabilities.json file
```
pyinstaller --noconfirm --onefile ^
  --add-data "templates;templates" ^
  --add-data "costs.json;." ^
  --add-data "receipts.csv;." ^
  --add-data "uploads;uploads" ^
  --add-data "C:\Users\*\AppData\Roaming\Python\Python313\site-packages\escpos\capabilities.json;escpos" ^
  app.py
```
