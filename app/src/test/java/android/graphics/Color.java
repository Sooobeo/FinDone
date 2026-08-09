package android.graphics;

import java.util.Locale;

/** Minimal JVM color arithmetic used while jlatexmath constructs a TeXIcon. */
public final class Color {
    public static int rgb(int red, int green, int blue) {
        return 0xFF000000
                | ((red & 0xFF) << 16)
                | ((green & 0xFF) << 8)
                | (blue & 0xFF);
    }

    public static int red(int color) {
        return (color >>> 16) & 0xFF;
    }

    public static int green(int color) {
        return (color >>> 8) & 0xFF;
    }

    public static int blue(int color) {
        return color & 0xFF;
    }

    public static int parseColor(String value) {
        switch (value.toLowerCase(Locale.ROOT)) {
            case "cyan": return 0xFF00FFFF;
            case "magenta": return 0xFFFF00FF;
            case "yellow": return 0xFFFFFF00;
            case "red": return 0xFFFF0000;
            case "green": return 0xFF00FF00;
            case "blue": return 0xFF0000FF;
            case "white": return 0xFFFFFFFF;
            case "black":
            default: return 0xFF000000;
        }
    }

    private Color() {
    }
}
