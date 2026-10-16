from django.core.management.base import BaseCommand
from products.email_service import send_sale_email
from products.firebase_client import get_store


class Command(BaseCommand):
    help = "Send or retry customer billing emails with attached PDF receipts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--bill",
            type=str,
            help="Send email for a specific bill number (e.g. AJ-000001).",
        )
        parser.add_argument(
            "--retry-failed",
            action="store_true",
            help="Retry bills where email_status is 'failed'.",
        )

    def handle(self, *args, **options):
        store = get_store()
        sales = store.list_sales()

        target_bill = options.get("bill")
        retry_failed = options.get("retry_failed")

        count = 0
        for s in sales:
            bill_num = s.get("bill_number") or s.get("bill")
            if target_bill and bill_num != target_bill:
                continue

            email = s.get("customer_email") or s.get("customerEmail")
            if not email:
                continue

            status = s.get("email_status")
            if status == "sent" and not target_bill:
                continue
            if status == "failed" and not retry_failed and not target_bill:
                continue

            self.stdout.write(f"Processing {bill_num} -> {email}...")
            res = send_sale_email(s)
            updates = {
                "email_status": res["status"],
                "email_sent_at": res.get("sent_at"),
                "email_error": res.get("error"),
            }
            try:
                store.update_sale(s["id"], updates)
                count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  [{res['status'].upper()}] {bill_num}: {res.get('error') or 'Sent successfully'}"
                    )
                )
            except Exception as e:
                self.stderr.write(f"  Failed to update sale record: {e}")

        self.stdout.write(self.style.SUCCESS(f"Finished. Processed {count} bill(s)."))
