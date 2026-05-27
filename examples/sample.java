// Kitchen sink Java sample.
// Purpose: compile supported constructs and expose unsupported constructs as warnings.

import java.io.BufferedReader;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

public class UserBenefitService {
    private static final int MAX_POINTS = 1000;
    private static final int PREMIUM_THRESHOLD = 100000;
    private int auditCounter = 0;

    /**
     * Supported-heavy method: guards, loops, data transforms, try/catch/finally and condition chains.
     */
    public BenefitResult getUserBenefit(
            String status,
            String rank,
            List<Purchase> purchaseHistory,
            boolean dryRun) {
        if (!status.equals("ACTIVE")) {
            throw new IllegalArgumentException("inactive user");
        }

        int totalAmount = 0;
        for (Purchase history : purchaseHistory) {
            totalAmount += history.getPrice();
        }

        for (int i = 0; i < purchaseHistory.size(); i++) {
            System.out.println(purchaseHistory.get(i).getCategory());
        }

        try {
            BufferedReader reader = new BufferedReader(new StringReader("config"));
            System.out.println(reader.readLine());
        } catch (Exception error) {
            System.err.println(error);
            throw new RuntimeException(error);
        } finally {
            auditCounter += 1;
            System.out.println("benefit calculation finished");
        }

        if (dryRun) {
            return new BenefitResult(0, "dry run", "basic");
        } else if (totalAmount >= PREMIUM_THRESHOLD && rank.equals("Gold")) {
            return new BenefitResult(MAX_POINTS, "premium benefit", "premium");
        } else if (totalAmount >= 50000) {
            return new BenefitResult(500, "standard benefit", "standard");
        } else {
            return new BenefitResult(100, "basic benefit", "basic");
        }
    }

    /**
     * Unsupported-heavy method: these constructs should be visible as extraction warnings today.
     */
    public int inspectUnsupportedFlow(User user, List<Integer> values) {
        int index = 0;
        int total = 0;

        while (index < values.size()) {
            total += values.get(index);
            index += 1;
        }

        do {
            total -= 1;
        } while (total > 1000);

        switch (user.status()) {
            case "ACTIVE":
                total += 10;
                break;
            case "BANNED":
                total -= 100;
                break;
            default:
                total += 0;
        }

        synchronized (this) {
            auditCounter += 1;
        }

        Function<Integer, Integer> doubleValue = value -> value * 2;
        List<Integer> normalized = new ArrayList<>();
        values.stream()
                .filter(value -> value > 0)
                .map(doubleValue)
                .forEach(normalized::add);

        return normalized.stream().reduce(total, Integer::sum);
    }

    public <T extends Number> int sumGenericValues(List<T> values) {
        int total = 0;
        for (T value : values) {
            total += value.intValue();
        }
        return total;
    }
}

record User(String id, String status, String rank, Map<String, String> metadata) {
}

class Purchase {
    private final int price;
    private final String category;

    Purchase(int price, String category) {
        this.price = price;
        this.category = category;
    }

    int getPrice() {
        return price;
    }

    String getCategory() {
        return category;
    }
}

class BenefitResult {
    private final int points;
    private final String message;
    private final String level;

    BenefitResult(int points, String message, String level) {
        this.points = points;
        this.message = message;
        this.level = level;
    }

    int getPoints() {
        return points;
    }

    String getMessage() {
        return message;
    }

    String getLevel() {
        return level;
    }
}

enum BenefitLevel {
    PREMIUM,
    STANDARD,
    BASIC
}

interface Notifier {
    void notify(String message);
}

