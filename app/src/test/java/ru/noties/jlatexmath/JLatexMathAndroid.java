package ru.noties.jlatexmath;

import android.content.Context;
import android.graphics.Typeface;

import java.io.InputStream;

/**
 * JVM-only resource adapter for the Android jlatexmath artifact.
 *
 * The production implementation reads through Android's AssetManager. The unit-test task puts the
 * APK's merged assets on its classpath, so the exact same XML/font metadata can be loaded without a
 * device or a process-wide filesystem property.
 */
public abstract class JLatexMathAndroid {
    private static final String BASE = "org/scilab/forge/jlatexmath/";

    public static void init(Context ignored) {
        // Android initialization is unnecessary when assets are classpath resources.
    }

    public static InputStream getResourceAsStream(String name) {
        final String resourceName = BASE + name;
        final ClassLoader contextLoader = Thread.currentThread().getContextClassLoader();
        InputStream stream = contextLoader == null
                ? null
                : contextLoader.getResourceAsStream(resourceName);
        if (stream == null) {
            stream = JLatexMathAndroid.class.getClassLoader().getResourceAsStream(resourceName);
        }
        if (stream == null) {
            throw new IllegalStateException("Missing bundled jlatexmath asset: " + resourceName);
        }
        return stream;
    }

    public static Typeface loadTypeface(String ignored) {
        // TeXIcon sizing uses XML metrics; no Canvas drawing or platform glyph rasterization occurs.
        return Typeface.DEFAULT;
    }

    private JLatexMathAndroid() {
    }
}
