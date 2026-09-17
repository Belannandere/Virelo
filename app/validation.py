from dataclasses import dataclass, field

from app.schemas import Invoice



AMOUNT_TOLERANCE = 0.02

LINE_ITEMS_TOLERANCE = 0.05


@dataclass
class ValidationResult:
    status: str  # "passed" или "review"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_passed(self) -> bool:
        return self.status == "passed"


def _approx_equal(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def validate_invoice(invoice: Invoice) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []


    if not invoice.supplier_name:
        errors.append("Supplier name is missing.")
    if not invoice.invoice_number:
        errors.append("Invoice number is missing.")
    if invoice.total is None:
        errors.append("Total is missing.")


    if not invoice.invoice_date:
        warnings.append("Invoice date is missing.")
    if not invoice.due_date:
        warnings.append("Due date is missing.")
    if not invoice.currency:
        warnings.append("Currency is missing.")


    if (
        invoice.subtotal is not None
        and invoice.tax is not None
        and invoice.total is not None
    ):
        expected = invoice.subtotal + invoice.tax
        if not _approx_equal(expected, invoice.total, AMOUNT_TOLERANCE):
            errors.append(
                f"Subtotal + tax ({expected:.2f}) does not match total "
                f"({invoice.total:.2f})."
            )

    # --- Line items ---
    if not invoice.line_items:
        warnings.append("No line items found.")
    else:
        incomplete = sum(
            1
            for li in invoice.line_items
            if li.description is None
            or li.quantity is None
            or li.unit_price is None
            or li.total is None
        )
        if incomplete:
            warnings.append(f"{incomplete} line item(s) have missing fields.")

        if invoice.subtotal is not None:
            line_sum = sum(
                li.total for li in invoice.line_items if li.total is not None
            )
            if line_sum > 0 and not _approx_equal(
                line_sum, invoice.subtotal, LINE_ITEMS_TOLERANCE
            ):
                warnings.append(
                    f"Sum of line items ({line_sum:.2f}) does not match "
                    f"subtotal ({invoice.subtotal:.2f})."
                )


    status = "passed" if not errors else "review"
    return ValidationResult(status=status, errors=errors, warnings=warnings)