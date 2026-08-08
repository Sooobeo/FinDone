plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

fun secret(name: String, propertyName: String): String? =
    providers.gradleProperty(propertyName).orNull ?: System.getenv(name)

val personalKeystorePath = secret("FINDONE_KEYSTORE_PATH", "findone.keystore.path")
val personalKeyAlias = secret("FINDONE_KEY_ALIAS", "findone.key.alias")
// Passwords are intentionally environment-only so they cannot be persisted in Gradle properties.
val personalStorePassword = System.getenv("FINDONE_STORE_PASSWORD")
val personalKeyPassword = System.getenv("FINDONE_KEY_PASSWORD")
val personalSigningReady = listOf(
    personalKeystorePath,
    personalKeyAlias,
    personalStorePassword,
    personalKeyPassword,
).all { !it.isNullOrBlank() }

android {
    namespace = "com.findone.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.findone.app"
        minSdk = 26
        targetSdk = 35
        versionCode = 2
        versionName = "0.3.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }

    signingConfigs {
        if (personalSigningReady) {
            create("personalRelease") {
                storeFile = rootProject.file(personalKeystorePath!!)
                storePassword = personalStorePassword
                keyAlias = personalKeyAlias
                keyPassword = personalKeyPassword
                enableV1Signing = true
                enableV2Signing = true
                enableV3Signing = true
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            signingConfig = signingConfigs.findByName("personalRelease")
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.03.01")
    implementation(composeBom)
    androidTestImplementation(composeBom)
    implementation("androidx.core:core-ktx:1.16.0")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.9.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.0")
    implementation("androidx.sqlite:sqlite-bundled:2.7.0")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("io.noties.markwon:core:4.6.2")
    implementation("io.noties.markwon:ext-latex:4.6.2")
    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
