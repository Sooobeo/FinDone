package android.graphics;

import android.content.res.AssetManager;

/** Minimal JVM font value needed by jlatexmath's TeXIcon metric construction. */
public class Typeface {
    public static final Typeface DEFAULT = new Typeface(false, false);

    private final boolean bold;
    private final boolean italic;

    public Typeface() {
        this(false, false);
    }

    private Typeface(boolean bold, boolean italic) {
        this.bold = bold;
        this.italic = italic;
    }

    public static Typeface createFromAsset(AssetManager ignored, String path) {
        return DEFAULT;
    }

    public static Typeface create(Typeface ignored, int style) {
        return new Typeface((style & 1) != 0, (style & 2) != 0);
    }

    public static Typeface create(String ignored, int style) {
        return create(DEFAULT, style);
    }

    public boolean isBold() {
        return bold;
    }

    public boolean isItalic() {
        return italic;
    }
}
