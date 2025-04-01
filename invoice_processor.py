from google.cloud import vision
import os
from datetime import datetime
import re
from typing import Dict, List, Optional
from google.oauth2 import service_account
import pdfplumber
import tempfile
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InvoiceProcessor:
    def __init__(self):
        credentials = service_account.Credentials.from_service_account_file(
            'credentials.json',
            scopes=['https://www.googleapis.com/auth/cloud-vision']
        )
        self.client = vision.ImageAnnotatorClient(credentials=credentials)

    def process_invoice(self, file_path: str) -> List[Dict]:
        """
        Process an invoice file and extract relevant information.
        Returns a list of line items with their details.
        """
        # Check if file is PDF
        is_pdf = file_path.lower().endswith('.pdf')
        
        if is_pdf:
            logger.info("Extracting text from PDF...")
            try:
                with pdfplumber.open(file_path) as pdf:
                    text = ""
                    for page in pdf.pages:
                        text += page.extract_text() + "\n"
                logger.info("Successfully extracted text from PDF")
            except Exception as e:
                logger.error(f"Error extracting text from PDF: {str(e)}")
                raise
        else:
            # For non-PDF files, use Google Cloud Vision
            with open(file_path, 'rb') as image_file:
                content = image_file.read()
            
            image = vision.Image(content=content)
            response = self.client.document_text_detection(image=image)
            
            if response.error.message:
                logger.error(f"Error during OCR: {response.error.message}")
                raise Exception(f"Error during OCR: {response.error.message}")
                
            text = response.full_text_annotation.text
        
        # Log the full extracted text for debugging
        logger.info("=" * 80)
        logger.info("FULL EXTRACTED TEXT:")
        logger.info("=" * 80)
        logger.info(text)
        logger.info("=" * 80)

        # Extract information
        invoice_date = self._extract_date(text)
        logger.info(f"Extracted date: {invoice_date}")
        
        invoice_number = self._extract_invoice_number(text)
        logger.info(f"Extracted invoice number: {invoice_number}")
        
        # Log text structure before line item extraction
        logger.info("Text structure before line item extraction:")
        lines = text.split('\n')
        for i, line in enumerate(lines):
            logger.info(f"Line {i}: {line}")
        
        line_items = self._extract_line_items(text)
        logger.info(f"Extracted {len(line_items)} line items")
        for item in line_items:
            logger.info(f"Line item: {item}")

        # Format the results
        results = []
        for item in line_items:
            results.append({
                'invoice_date': invoice_date,
                'invoice_number': invoice_number,
                'expense_description': item['description'],
                'expense_qty': item['quantity'],
                'expense_amount': item['amount'],
                'total_expense_cost': item['total'],
                'date_accessed': datetime.now().strftime('%Y-%m-%d')  # Only show date
            })

        return results

    def _extract_date(self, text: str) -> str:
        """Extract the invoice date from the text."""
        # Common date patterns
        date_patterns = [
            r'\d{2}/\d{2}/\d{4}',
            r'\d{2}-\d{2}-\d{4}',
            r'\d{4}/\d{2}/\d{2}',
            r'\d{4}-\d{2}-\d{2}',
            r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        
        return datetime.now().strftime('%Y-%m-%d')

    def _extract_invoice_number(self, text: str) -> str:
        """Extract the invoice number from the text."""
        # Look for Invoice #: pattern
        match = re.search(r'Invoice\s*#:\s*(\d+)', text)
        if match:
            return match.group(1)
        
        # Look for Invoice #
        match = re.search(r'Invoice\s*#\s*(\d+)', text)
        if match:
            return match.group(1)
            
        # Look for specific patterns near "Invoice"
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if 'INVOICE' in line.upper():
                # Check next few lines for the invoice number
                for j in range(i, min(i + 5, len(lines))):
                    if '#' in lines[j]:
                        # Extract the number after #
                        parts = lines[j].split('#')
                        if len(parts) > 1:
                            # Extract just the digits
                            number = re.search(r'(\d+)', parts[1])
                            if number:
                                return number.group(1)
        
        return 'Invoice'

    def _extract_line_items(self, text: str) -> List[Dict]:
        """Extract line items from the text."""
        lines = text.split('\n')
        line_items = []
        
        # Log the start of line item extraction
        logger.info("Starting line item extraction...")
        
        # First, clean up the lines and remove any empty ones
        lines = [line.strip() for line in lines if line.strip()]
        
        # Find the services section
        services_start = -1
        services_end = -1
        
        # Common section headers that might indicate where line items start
        section_headers = [
            'Services',
            'Items',
            'Description',
            'Product',
            'Details',
            'Charges',
            'Line Items'
        ]
        
        # Common headers that indicate the end of line items
        end_headers = [
            'Services Subtotal:',
            'Subtotal:',
            'Total:',
            'Balance Due',
            'Amount Due',
            'Payment Terms',
            'Terms',
            'Notes'
        ]
        
        # Look for the section header and its associated column headers
        for i, line in enumerate(lines):
            # Check if line contains any of our section headers
            if any(header.lower() in line.lower() for header in section_headers):
                # Look ahead for column headers
                for j in range(i, min(i + 5, len(lines))):
                    # Common column header combinations
                    if any([
                        all(col in lines[j].lower() for col in ['date', 'description']),
                        all(col in lines[j].lower() for col in ['item', 'amount']),
                        all(col in lines[j].lower() for col in ['quantity', 'price']),
                        all(col in lines[j].lower() for col in ['description', 'rate']),
                    ]):
                        services_start = j + 1
                        logger.info(f"Found header row at line {j}: {lines[j]}")
                        break
                if services_start != -1:
                    break
        
        if services_start == -1:
            logger.info("Could not find section header, trying alternative approaches")
            # Try to find the first line that matches common line item patterns
            for i, line in enumerate(lines):
                # Check for date-prefixed lines
                if re.match(r'\d{2}[-/]\d{2}[-/]\d{2}', line):
                    services_start = i
                    logger.info(f"Found date-prefixed line at {i}: {line}")
                    break
                # Check for numbered items (e.g., "1.", "1)", "(1)")
                elif re.match(r'^\s*(?:\d+[\.)]\s+|\(\d+\)\s+)', line):
                    services_start = i
                    logger.info(f"Found numbered item at {i}: {line}")
                    break
                # Check for lines with amount patterns (e.g., "$100.00", "100.00")
                elif re.search(r'\$?\s*\d{1,3}(?:,\d{3})*\.\d{2}\b', line):
                    services_start = i
                    logger.info(f"Found amount pattern at {i}: {line}")
                    break
        
        if services_start == -1:
            logger.info("Could not find line items section")
            return line_items

        # Find the end of the section
        for i in range(services_start, len(lines)):
            if any(header.lower() in lines[i].lower() for header in end_headers):
                services_end = i
                break
        
        if services_end == -1:
            services_end = len(lines)

        # Process each line in the section
        current_item = None
        for i in range(services_start, services_end):
            line = lines[i].strip()
            logger.info(f"Processing line {i}: {line}")
            
            # Skip empty lines or summary lines
            if not line or any(header.lower() in line.lower() for header in end_headers):
                if current_item:
                    line_items.append(current_item)
                    current_item = None
                continue
            
            try:
                # Split the line and clean up parts
                parts = line.split()
                
                # Check if this is a new line item
                is_new_item = (
                    re.match(r'\d{2}[-/]\d{2}[-/]\d{2}', line) or  # Date prefix
                    re.match(r'^\s*(?:\d+[\.)]\s+|\(\d+\)\s+)', line) or  # Numbered item
                    (len(parts) >= 3 and re.search(r'\$?\s*\d{1,3}(?:,\d{3})*\.\d{2}\b', line))  # Has amount
                )
                
                if is_new_item:
                    # Add previous item if exists
                    if current_item:
                        line_items.append(current_item)
                    
                    # Find all numbers in the line (including those with $ and ,)
                    numbers = []
                    number_indices = []
                    for idx, part in enumerate(parts):
                        clean_part = part.replace('$', '').replace(',', '')
                        if re.match(r'^-?\d*\.?\d+$', clean_part):
                            numbers.append(float(clean_part))
                            number_indices.append(idx)
                    
                    if len(numbers) >= 2:  # Need at least rate and total
                        # Handle different number arrangements
                        if len(numbers) >= 3:
                            # Assume last three numbers are quantity, rate, total
                            quantity = numbers[-3]
                            rate = numbers[-2]
                            total = numbers[-1]
                        else:
                            # Assume last two numbers are rate and total
                            rate = numbers[-2]
                            total = numbers[-1]
                            # Calculate quantity
                            quantity = round(total / rate, 2) if rate != 0 else 1
                        
                        # Get description
                        # Skip date or number prefix if present
                        start_idx = 1 if re.match(r'\d{2}[-/]\d{2}[-/]\d{2}', parts[0]) else 0
                        start_idx = start_idx + 1 if re.match(r'^\s*(?:\d+[\.)]\s*|\(\d+\)\s*)', parts[0]) else start_idx
                        
                        # Description is everything between start and first number
                        first_number_idx = min(number_indices)
                        description = ' '.join(parts[start_idx:first_number_idx])
                        
                        current_item = {
                            'description': description,
                            'quantity': quantity,
                            'amount': rate,
                            'total': total
                        }
                        logger.info(f"Found line item: {current_item}")
                
                elif current_item:
                    # Check if this line doesn't contain amounts and looks like a description continuation
                    if not re.search(r'\$?\s*\d{1,3}(?:,\d{3})*\.\d{2}\b', line):
                        current_item['description'] += ' ' + line
                        logger.info(f"Added continuation to description: {line}")
            
            except Exception as e:
                logger.error(f"Error processing line item '{line}': {str(e)}")
                current_item = None

        # Add the last item if we have one
        if current_item:
            line_items.append(current_item)
            logger.info("Added final line item")

        logger.info(f"Extracted {len(line_items)} line items")
        for item in line_items:
            logger.info(f"Final line item: {item}")
        
        return line_items 