/** Executable smoke-check harness, not a JUnit replacement or business acceptance report. */
public final class OrderTotalCheck {
    public static void main(String[] args) {
        long actual = OrderTotal.totalCents(125, 275);
        if (actual != 400) {
            throw new AssertionError("expected 400 cents, observed " + actual);
        }
        if (OrderTotal.totalCents() != 0) {
            throw new AssertionError("empty order must total 0");
        }
        boolean rejected = false;
        try {
            OrderTotal.totalCents(-5);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        if (!rejected) {
            throw new AssertionError("negative line amounts must be rejected");
        }
        System.out.println("Java order-total smoke checks: passed (3 checks)");
    }
}
