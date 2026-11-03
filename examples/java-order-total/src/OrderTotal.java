/** Minimal illustrative production logic: sum non-negative line item amounts in cents. */
public final class OrderTotal {
    private OrderTotal() {}

    public static long totalCents(long... amounts) {
        long total = 0;
        for (long amount : amounts) {
            if (amount < 0) {
                throw new IllegalArgumentException("negative amount");
            }
            total = Math.addExact(total, amount);
        }
        return total;
    }
}
