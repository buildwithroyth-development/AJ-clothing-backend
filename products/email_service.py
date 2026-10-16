import os
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid
from io import BytesIO
from xml.sax.saxutils import escape

def get_default_store():
    """Retrieve store defaults, prioritizing environment variables when set."""
    return {
        'name': (
            os.getenv('STORE_NAME')
            or os.getenv('EMAIL_SENDER_NAME')
            or 'AJ Clothing Store'
        ).strip(),
        'tagline': os.getenv('STORE_TAGLINE', '').strip(),
        'address': os.getenv('STORE_ADDRESS', 'Commercial Street, Bangalore').strip(),
        'phone': os.getenv('STORE_PHONE', '+91 98765 43210').strip(),
        'email': (
            os.getenv('STORE_EMAIL')
            or os.getenv('EMAIL_HOST_USER')
            or 'contact@ajclothing.com'
        ).strip(),
        'gstin': os.getenv('STORE_GSTIN', '').strip(),
        'note': os.getenv('STORE_NOTE', 'Thank you for shopping with us!').strip(),
    }


def resolve_store_info(custom_store=None):
    """Merge environment configs, system defaults, and any database/custom settings."""
    base = get_default_store()
    if not custom_store or not isinstance(custom_store, dict):
        return base
    merged = dict(base)
    for k, v in custom_store.items():
        if v is not None and str(v).strip():
            merged[k] = str(v).strip()
    return merged


DEFAULT_STORE = get_default_store()


def invoice_pdf(sale, store=None):
    """Generate an itemized PDF receipt in memory using ReportLab.

    Returns the raw PDF bytes.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    store = resolve_store_info(store)
    buffer = BytesIO()
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'StoreTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#221b18'),
        fontName='Helvetica-Bold',
    )
    meta_style = ParagraphStyle(
        'StoreMeta',
        parent=styles['Normal'],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#6b615c'),
    )
    section_title = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#221b18'),
        fontName='Helvetica-Bold',
    )
    normal = ParagraphStyle(
        'ReceiptNormal',
        parent=styles['Normal'],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#221b18'),
    )
    bold = ParagraphStyle(
        'ReceiptBold',
        parent=normal,
        fontName='Helvetica-Bold',
    )
    th_style = ParagraphStyle(
        'TableHeader',
        parent=normal,
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=colors.HexColor('#221b18'),
    )

    def p(text, style=normal):
        return Paragraph(escape(str(text or '')).replace('\n', '<br/>'), style)

    bill_num = sale.get('bill_number') or sale.get('bill') or 'AJ-000000'
    raw_date = sale.get('created_at') or sale.get('at') or ''
    date_display = raw_date
    if raw_date:
        try:
            dt = datetime.fromisoformat(raw_date.replace('Z', '+00:00'))
            date_display = dt.strftime('%d %b %Y, %I:%M %p')
        except Exception:
            date_display = raw_date

    logo_path = os.path.join(os.path.dirname(__file__), 'assets', 'AJ_logo.png')
    store_meta_blocks = [
        p(store.get('name') or 'AJ Clothing Store', title_style),
    ]

    header_details = [
        store.get('tagline'),
        store.get('address'),
        ' · '.join(filter(None, [store.get('phone'), store.get('email')])),
        f"GSTIN: {store.get('gstin')}" if store.get('gstin') else '',
    ]
    for detail in header_details:
        if detail:
            store_meta_blocks.append(p(detail, meta_style))

    if os.path.exists(logo_path):
        try:
            from reportlab.platypus import Image as RLImage
            logo_img = RLImage(logo_path, width=22 * mm, height=22 * mm)
            header_table = Table([[logo_img, store_meta_blocks]], colWidths=[26 * mm, 154 * mm])
            header_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            blocks = [header_table]
        except Exception:
            blocks = list(store_meta_blocks)
    else:
        blocks = list(store_meta_blocks)

    blocks.extend([
        Spacer(1, 4 * mm),
        p(f"SALES RECEIPT · {bill_num}", section_title),
        Spacer(1, 2 * mm),
    ])

    # Customer & Bill metadata
    cust_name = sale.get('customer_name') or sale.get('customerName') or 'Walk-in customer'
    cust_mobile = sale.get('customer_mobile') or sale.get('customerMobile') or '—'
    cust_email = sale.get('customer_email') or sale.get('customerEmail') or '—'

    meta_table_data = [
        [p("Bill Number:", bold), p(bill_num), p("Date & Time:", bold), p(date_display)],
        [p("Customer:", bold), p(cust_name), p("Mobile:", bold), p(cust_mobile)],
        [p("Customer Email:", bold), p(cust_email), p("Payment Mode:", bold), p(str(sale.get('payment_method') or sale.get('payment') or 'Cash'))],
    ]
    meta_table = Table(meta_table_data, colWidths=[30 * mm, 55 * mm, 30 * mm, 65 * mm])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    blocks.extend([meta_table, Spacer(1, 5 * mm)])

    # Items table
    items_rows = [
        [p("#", th_style), p("Item", th_style), p("Qty", th_style), p("Rate (INR)", th_style), p("Amount (INR)", th_style)]
    ]

    items = sale.get('items') or []
    for idx, it in enumerate(items, 1):
        name = it.get('name') or it.get('product_name') or 'Product'
        details = ' · '.join(filter(None, [
            it.get('colour'),
            f"Size {it.get('size')}" if it.get('size') else '',
            it.get('sku'),
        ]))
        item_text = f"<b>{escape(str(name))}</b>"
        if details:
            item_text += f"<br/><font color='#6b615c' size='8'>{escape(details)}</font>"

        qty = str(it.get('qty', it.get('quantity', 1)))
        price = f"{float(it.get('price', 0)):.2f}"
        amount = f"{float(it.get('line_total', it.get('amount', 0))):.2f}"

        items_rows.append([
            p(str(idx)),
            Paragraph(item_text, normal),
            p(qty),
            p(price),
            p(amount),
        ])

    items_table = Table(items_rows, colWidths=[10 * mm, 85 * mm, 20 * mm, 30 * mm, 35 * mm], repeatRows=1)
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f5f0')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#221b18')),
        ('LINEBELOW', (0, 1), (-1, -1), 0.5, colors.HexColor('#e5dfd8')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    blocks.extend([items_table, Spacer(1, 5 * mm)])

    # Financial totals
    subtotal = f"INR {float(sale.get('subtotal', 0)):.2f}"
    discount = f"INR {float(sale.get('discount', 0)):.2f}"
    total = f"INR {float(sale.get('total', 0)):.2f}"

    totals_rows = [
        [p(""), p("Subtotal:", bold), p(subtotal)],
        [p(""), p(f"Discount ({sale.get('discount_percent', 0)}%):", normal), p(discount)],
    ]

    rounding = sale.get('rounding_adjustment') or sale.get('adjustment')
    if rounding and float(rounding) != 0:
        totals_rows.append([p(""), p("Rounding adjustment:", normal), p(f"INR {float(rounding):.2f}")])

    totals_rows.append([p(""), p("Final Total:", section_title), p(total, section_title)])

    totals_table = Table(totals_rows, colWidths=[95 * mm, 50 * mm, 35 * mm])
    totals_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
    ]))
    blocks.extend([totals_table, Spacer(1, 6 * mm)])

    # Footer note
    raw_note = store.get('note') or 'Thank you for shopping with AJ Clothing!'
    clean_note = re.sub(r'(?i)returns?\s+within\s+\d+\s+days[^\n.]*\.?', '', raw_note).strip()
    note = clean_note or 'Thank you for shopping with AJ Clothing!'
    blocks.append(p(note, meta_style))

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Receipt-{bill_num}",
        author=store.get('name') or 'AJ Clothing',
    )
    doc.build(blocks)
    return buffer.getvalue()


def bill_text(sale, store=None):
    """Format concise plaintext email body."""
    store = resolve_store_info(store)
    customer = sale.get('customer_name') or sale.get('customerName') or 'Valued Customer'
    bill_num = sale.get('bill_number') or sale.get('bill') or 'AJ-000000'
    store_name = store.get('name') or 'AJ Clothing'

    lines = [
        f"Dear {customer},",
        "",
        "Thank you for shopping with us! We truly appreciate your visit and hope you love your new purchase.",
        "",
        f"Please find your bill receipt (Bill-{bill_num}.pdf) attached as a PDF to this email.",
        "",
        "We look forward to serving you again soon!",
        "",
        "Warm regards,",
        f"The {store_name} Team",
    ]

    return "\n".join(lines)


def bill_html(sale, store=None, logo_cid=None):
    """Generate a clean, minimal HTML email body focusing on greeting, friendly note, PDF attachment notice, and sign-off."""
    store = resolve_store_info(store)
    customer = escape(str(sale.get('customer_name') or sale.get('customerName') or 'Valued Customer'))
    bill_num = escape(str(sale.get('bill_number') or sale.get('bill') or 'AJ-000000'))
    store_name = escape(str(store.get('name') or 'AJ Clothing'))
    store_address = escape(str(store.get('address') or ''))
    store_phone = escape(str(store.get('phone') or ''))
    store_email = escape(str(store.get('email') or ''))

    logo_img_tag = (
        f'<img src="cid:{logo_cid}" alt="{store_name}" width="52" height="52" style="width: 52px; height: 52px; max-width: 52px; max-height: 52px; display: block; margin-bottom: 12px; border: 0; outline: none; text-decoration: none; border-radius: 50%;" />'
        if logo_cid
        else ''
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Your Receipt - {store_name}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f7f5f2; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1c1917;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color: #f7f5f2; padding: 32px 12px;">
    <tr>
      <td align="center">
        <!-- Main Card Container -->
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width: 560px; background-color: #ffffff; border-radius: 12px; border: 1px solid #e7e2db; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.03);">

          <!-- Brand / Sender Header with Logo -->
          <tr>
            <td style="padding: 26px 32px 20px; background-color: #ffffff; border-bottom: 1px solid #f0ece8;">
              {logo_img_tag}
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; color: #1c1917; letter-spacing: 0.5px;">{store_name}</h1>
              <div style="font-size: 12px; color: #78716c; margin-top: 4px; line-height: 1.4;">
                {store_address}{f" · {store_phone}" if store_phone else ""}{f" · {store_email}" if store_email else ""}
              </div>
            </td>
          </tr>

          <!-- Message Body -->
          <tr>
            <td style="padding: 28px 32px 24px;">
              <p style="margin: 0 0 16px; font-size: 15px; font-weight: 600; color: #1c1917;">
                Dear {customer},
              </p>

              <p style="margin: 0 0 20px; font-size: 14px; line-height: 1.6; color: #44403c;">
                Thank you for shopping with us! We truly appreciate your visit and hope you love your new purchase.
              </p>

              <!-- PDF Attachment Notice -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color: #f0f7ff; border: 1px solid #bfdbfe; border-left: 4px solid #2563eb; border-radius: 6px; margin: 20px 0 24px;">
                <tr>
                  <td style="padding: 14px 18px;">
                    <div style="font-size: 14px; font-weight: 600; color: #1e3a8a;">
                      📎 Please find your bill attached as a PDF
                    </div>
                    <div style="font-size: 13px; color: #3b82f6; margin-top: 4px; line-height: 1.4;">
                      Your official receipt <strong>Bill-{bill_num}.pdf</strong> is attached to this email. You can download and save it for your records.
                    </div>
                  </td>
                </tr>
              </table>

              <!-- Warm Sign-off -->
              <p style="margin: 0; font-size: 14px; color: #44403c; line-height: 1.6;">
                We look forward to serving you again soon!<br/><br/>
                Warm regards,<br/>
                <strong style="color: #1c1917;">The {store_name} Team</strong>
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding: 16px 32px; background-color: #faf8f5; border-top: 1px solid #f0ece8; text-align: center; font-size: 11px; color: #a8a29e;">
              This is an automated sales receipt notification from {store_name}.
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_sale_email(sale, store=None, recipient=None):
    """Send an itemized receipt email with HTML template, sender logo, and generated PDF attached.

    Returns:
        dict: {'status': 'sent'|'failed'|'skipped', 'recipient': ..., 'message_id': ..., 'sent_at': ..., 'error': ...}
    """
    recipient = recipient or sale.get('customer_email') or sale.get('customerEmail')
    if not recipient or not str(recipient).strip():
        return {
            'status': 'skipped',
            'recipient': '',
            'message_id': '',
            'sent_at': None,
            'error': 'No customer email address provided.',
        }

    recipient = str(recipient).strip()
    host = os.getenv('EMAIL_HOST', 'smtp.gmail.com').strip()
    port = int(os.getenv('EMAIL_PORT', '587').strip())
    sender = os.getenv('EMAIL_HOST_USER', '').strip()
    password = os.getenv('EMAIL_HOST_PASSWORD', '').strip()
    sender_name = os.getenv('EMAIL_SENDER_NAME', 'AJ Clothing').strip()

    if not sender or not password:
        return {
            'status': 'failed',
            'recipient': recipient,
            'message_id': '',
            'sent_at': None,
            'error': 'EMAIL_HOST_USER or EMAIL_HOST_PASSWORD is not configured in backend .env.',
        }

    bill_num = sale.get('bill_number') or sale.get('bill') or 'AJ-000000'

    try:
        pdf_bytes = invoice_pdf(sale, store)
    except Exception as exc:
        return {
            'status': 'failed',
            'recipient': recipient,
            'message_id': '',
            'sent_at': None,
            'error': f'PDF generation failed: {exc}',
        }

    try:
        domain = sender.split('@')[-1] if '@' in sender else 'ajclothing.com'
        sale_key = sale.get('id') or bill_num
        message_id_header = f"<aj-bill-{sale_key}@{domain}>"

        logo_path = os.path.join(os.path.dirname(__file__), 'assets', 'AJ_logo.png')
        has_logo = os.path.exists(logo_path)

        # RFC-compliant unique Content-ID for inline embedding
        if has_logo:
            logo_msgid = make_msgid(domain=domain)
            logo_cid = logo_msgid.strip('<>')
        else:
            logo_msgid = None
            logo_cid = None

        # Root multipart/mixed email container
        msg = MIMEMultipart('mixed')
        msg['From'] = f'"{sender_name}" <{sender}>' if sender_name else sender
        msg['To'] = recipient
        msg['Subject'] = f"Thank you for shopping with {sender_name}! Receipt #{bill_num}"
        msg['Message-ID'] = message_id_header

        # Alternative container for plain text and rich HTML
        alt_container = MIMEMultipart('alternative')

        # 1. Plain text fallback
        alt_container.attach(MIMEText(bill_text(sale, store), 'plain', 'utf-8'))

        # 2. HTML email body with related inline logo
        if has_logo:
            related_container = MIMEMultipart('related')
            html_part = MIMEText(bill_html(sale, store, logo_cid=logo_cid), 'html', 'utf-8')
            related_container.attach(html_part)

            try:
                with open(logo_path, 'rb') as lf:
                    logo_data = lf.read()
                img_part = MIMEImage(logo_data, 'png')
                img_part.add_header('Content-ID', f'<{logo_cid}>')
                # Explicitly inline without filename so email clients don't show it as a downloadable attachment
                img_part.add_header('Content-Disposition', 'inline')
                related_container.attach(img_part)
            except Exception:
                pass

            alt_container.attach(related_container)
        else:
            html_part = MIMEText(bill_html(sale, store, logo_cid=None), 'html', 'utf-8')
            alt_container.attach(html_part)

        msg.attach(alt_container)

        # 3. PDF bill attachment (marked as download attachment)
        pdf_part = MIMEApplication(pdf_bytes, 'pdf')
        pdf_part.add_header(
            'Content-Disposition',
            'attachment',
            filename=f"Bill-{bill_num}.pdf",
        )
        msg.attach(pdf_part)

        raw = msg.as_bytes()

        smtp = smtplib.SMTP(host, port, timeout=25)
        try:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()

            # Support Google App passwords with or without spaces
            try:
                smtp.login(sender, password)
            except smtplib.SMTPAuthenticationError:
                if ' ' in password:
                    smtp.login(sender, password.replace(' ', ''))
                else:
                    raise

            refused = smtp.sendmail(sender, [recipient], raw)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
        finally:
            try:
                smtp.quit()
            except Exception:
                try:
                    smtp.close()
                except Exception:
                    pass

        return {
            'status': 'sent',
            'recipient': recipient,
            'message_id': str(msg['Message-ID']),
            'sent_at': datetime.now(timezone.utc).isoformat(),
            'error': None,
        }

    except Exception as exc:
        return {
            'status': 'failed',
            'recipient': recipient,
            'message_id': '',
            'sent_at': None,
            'error': str(exc),
        }
