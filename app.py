from flask import Flask, request, render_template, jsonify, send_from_directory, session, redirect, url_for
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.cloud import vision
from invoice_processor import InvoiceProcessor
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Required for sessions

# Ensure the uploads directory exists
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Allowed file extensions
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

# Google Sheets API setup
SAMPLE_SPREADSHEET_ID = '15HbBXkN3D8SryYxbNYtrVrohzbtt84_0WHpeSt0H7DU'  # Google Sheet ID
RANGE_NAME = 'Sheet1!A2:G'  # Starting from A2 to leave room for headers

# Password for the application
APP_PASSWORD = "43north"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'authenticated' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == APP_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Invalid password")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Allowed types: ' + ', '.join(ALLOWED_EXTENSIONS)}), 400
        
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # Process the invoice
            processor = InvoiceProcessor()
            results = processor.process_invoice(filepath)
            
            # Set up Google Sheets
            credentials = service_account.Credentials.from_service_account_file(
                'credentials.json',
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            service = build('sheets', 'v4', credentials=credentials)
            spreadsheet_id = '15HbBXkN3D8SryYxbNYtrVrohzbtt84_0WHpeSt0H7DU'
            
            # Define headers
            headers = [
                ['Invoice Date', 'Invoice Number', 'Expense Description', 
                 'Expense Quantity', 'Expense Amount', 'Total Expense Cost', 
                 'Date Accessed']
            ]
            
            # Check if headers exist
            header_range = 'Sheet1!A1:G1'
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=header_range
            ).execute()
            
            if 'values' not in result:
                # Add headers if they don't exist
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=header_range,
                    valueInputOption='RAW',
                    body={'values': headers}
                ).execute()
                
                # Apply header styling
                requests = [{
                    'repeatCell': {
                        'range': {
                            'sheetId': 0,  # Assuming first sheet
                            'startRowIndex': 0,
                            'endRowIndex': 1,
                            'startColumnIndex': 0,
                            'endColumnIndex': 7
                        },
                        'cell': {
                            'userEnteredFormat': {
                                'backgroundColor': {
                                    'red': 0.9,
                                    'green': 0.9,
                                    'blue': 0.9
                                },
                                'textFormat': {
                                    'bold': True
                                }
                            }
                        },
                        'fields': 'userEnteredFormat(backgroundColor,textFormat)'
                    }
                },
                {
                    'updateSheetProperties': {
                        'properties': {
                            'sheetId': 0,
                            'gridProperties': {
                                'frozenRowCount': 1
                            }
                        },
                        'fields': 'gridProperties.frozenRowCount'
                    }
                }]
                
                service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={'requests': requests}
                ).execute()
            
            # Prepare the data for Google Sheets
            values = []
            for item in results:
                values.append([
                    item['invoice_date'],
                    item['invoice_number'],
                    item['expense_description'],
                    item['expense_qty'],
                    item['expense_amount'],
                    item['total_expense_cost'],
                    item['date_accessed']
                ])
            
            # Append the data to the sheet
            service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range='Sheet1!A2:G',  # Start from row 2 to preserve headers
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': values}
            ).execute()
            
            # Clean up the uploaded file
            os.remove(filepath)
            
            return jsonify({
                'message': f'Invoice processed successfully! {len(results)} items extracted.',
                'items': results
            })
            
        except Exception as e:
            # Clean up the uploaded file in case of error
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({'error': str(e)}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000) 