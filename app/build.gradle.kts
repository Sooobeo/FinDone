plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Local release automation can override these values for an installable build from an
// exact Git commit. Ordinary/manual builds keep the declared application version.
val declaredVersionCode = 2
val declaredVersionName = "0.3.0"
val declaredReleaseSummary = "시작 화면·용어집 스크롤 개선"
val appVersionCode = providers.gradleProperty("findone.versionCode").orNull?.let { value ->
    value.toIntOrNull()?.takeIf { it in 1..2_100_000_000 }
        ?: throw GradleException("findone.versionCode must be an integer from 1 to 2100000000")
} ?: declaredVersionCode
val appVersionName = providers.gradleProperty("findone.versionName").orNull?.also { value ->
    if (value.isBlank()) throw GradleException("findone.versionName must not be blank")
} ?: declaredVersionName

android {
    namespace = "com.findone.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.findone.app"
        minSdk = 26
        targetSdk = 35
        versionCode = appVersionCode
        versionName = appVersionName
        buildConfigField("String", "RELEASE_SUMMARY", "\"$declaredReleaseSummary\"")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    sourceSets.getByName("testDebug").resources.srcDir(
        layout.buildDirectory.dir("intermediates/assets/debug/mergeDebugAssets")
    )
    sourceSets.getByName("testRelease").resources.srcDir(
        layout.buildDirectory.dir("intermediates/assets/release/mergeReleaseAssets")
    )
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.03.01")
    implementation(composeBom)
    androidTestImplementation(composeBom)
    implementation("androidx.core:core-ktx:1.16.0")
    implementation("androidx.core:core-splashscreen:1.2.0")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.9.0")
    implementation("androidx.sqlite:sqlite-bundled:2.7.0")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("io.noties.markwon:core:4.6.2")
    implementation("io.noties.markwon:ext-latex:4.6.2")
    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.xerial:sqlite-jdbc:3.49.1.0")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}

// The LaTeX corpus regression test consumes the same merged database and jlatexmath assets that
// are packaged in each APK variant. Processing them as test resources avoids copies in source
// control and makes dependency upgrades visible to the JVM test, including clean release builds.
tasks.matching { it.name == "processDebugUnitTestJavaRes" }.configureEach {
    dependsOn("mergeDebugAssets")
}
tasks.matching { it.name == "processReleaseUnitTestJavaRes" }.configureEach {
    dependsOn("mergeReleaseAssets")
}
