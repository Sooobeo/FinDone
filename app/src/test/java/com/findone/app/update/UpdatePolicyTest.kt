package com.findone.app.update

import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Test

class UpdatePolicyTest {
    private val installed = AppIdentity(
        packageName = "com.findone.app",
        versionCode = 2,
        signerSha256 = setOf("trusted-certificate"),
    )

    @Test
    fun `higher version with same package and signer is allowed`() {
        val candidate = installed.copy(versionCode = 3)

        assertSame(UpdateDecision.Allowed, UpdatePolicy.evaluate(installed, candidate))
    }

    @Test
    fun `different package is rejected`() {
        val candidate = installed.copy(packageName = "example.attacker", versionCode = 3)

        assertRejected(UpdateRejection.PACKAGE_MISMATCH, candidate)
    }

    @Test
    fun `same version is rejected`() {
        assertRejected(UpdateRejection.VERSION_NOT_NEWER, installed)
    }

    @Test
    fun `lower version is rejected`() {
        assertRejected(UpdateRejection.VERSION_NOT_NEWER, installed.copy(versionCode = 1))
    }

    @Test
    fun `missing signer is rejected`() {
        assertRejected(
            UpdateRejection.SIGNING_CERTIFICATE_MISSING,
            installed.copy(versionCode = 3, signerSha256 = emptySet()),
        )
    }

    @Test
    fun `different signer is rejected`() {
        assertRejected(
            UpdateRejection.SIGNING_CERTIFICATE_MISMATCH,
            installed.copy(versionCode = 3, signerSha256 = setOf("other-certificate")),
        )
    }

    @Test
    fun `only callback for the pending package installer session is accepted`() {
        assertEquals(true, InstallCallbackPolicy.belongsToPendingSession(42, 42))
        assertEquals(false, InstallCallbackPolicy.belongsToPendingSession(42, 41))
        assertEquals(false, InstallCallbackPolicy.belongsToPendingSession(null, 42))
        assertEquals(false, InstallCallbackPolicy.belongsToPendingSession(42, -1))
    }

    private fun assertRejected(reason: UpdateRejection, candidate: AppIdentity) {
        assertEquals(
            UpdateDecision.Rejected(reason),
            UpdatePolicy.evaluate(installed, candidate),
        )
    }
}
