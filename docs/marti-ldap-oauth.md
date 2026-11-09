# Marti administration with LDAP and OAuth

LDAP is the account/password authority. `takctl_admin_user` selects the installer administrator; `takctl_admin_password` is the canonical protected credential used to provision LDAP and obtain OAuth tokens. Do not duplicate it in `marti_api_password` or UserAuthenticationFile.xml.

The LDAP writer adds administrative users to `ldap_admin_group` (default `TAKS_ADMIN`). CoreConfig renders that exact value as `auth/ldap/@adminGroup`. Ordinary channel edits preserve existing administrator-group membership. Ordinary users are not added to that group.

TAKS administrative Marti requests use `takctl.services.marti_api`: form-encoded password grant at `/oauth/token`, cached short-lived Bearer tokens, one refresh after HTTP 401, verified HTTPS and no redirects. User/group CRUD in LDAP mode remains direct LDAP; it must not use Marti's file-user-management API to create a parallel directory. The legacy `marti_api_username/password` configuration is unused by the canonical administrative client.

Business MCP's orchestrator-side diagnostics obtain tokens from the same canonical bootstrap identity. The node Business domain exposes a fixed read-only Marti session diagnostic through the shared TAKCTL client. MCP does not return credentials or tokens.

Martine currently uploads/reads mission packages and sends CoT with her own non-admin client certificate. Those Marti sync endpoints do not require ROLE_ADMIN. Her ordinary identity must remain outside `TAKS_ADMIN`; future approved administrative tools should delegate through the shared administrative client instead of granting her CoT identity broad privileges.

## Validation

The post-install Business MCP gate runs offline OAuth/group tests and three live checks: administrator access to ROLE_ADMIN-protected `/Marti/api/inputs` returns 200, ordinary Martine access to that same endpoint returns 403, and the administrator has no XML password copy. A failure aborts installation.

## Deployment

The orchestrator runtime and bundle source are separate deployments. Updating the former alone does not migrate the running TAK node. The node needs the updated LDAP group membership, rendered CoreConfig, and TAKCTL code; apply these together and then run the live checks. Preserve existing LDAP accounts, certificates and onboarding state when replacing a node.

## Auto-enroll ZIP investigation

The current middle QR resolves to a ZIP containing `certs/config.pref` and `certs/caCert.p12`, with enrollment enabled and a connection-specific truststore password. It contains no client certificate or embedded LDAP login credentials. Both PKCS#12 files parse; the hybrid enrollment truststore includes the internal TAK CA and public TLS chain. The existing package checker incorrectly warns about a missing unindexed `caPassword` when the valid connection-specific key is `caPassword0`.

Node logs confirmed Alexander's successful LDAP enrollment and subsequent CoT subscription. Enrollment configuration returned 200 using his credentials. These observations do not prove the Android ZIP importer completed enrollment. Capture ATAK-side ImportCertSort, PreferenceControl, CertificateEnrollmentClient and CertificateConfigOperation logs during a failing ZIP import. Do not infer a server failure merely from the red connection indicator, or treat an HTTPS request through an egress proxy as proof that the handset trusts the ZIP's CA chain.

Reading `/Marti/api/subscriptions/all` alone is not proof of administrator privileges: TAK permits authenticated non-admin access to that endpoint. Administrator diagnostics must check a ROLE_ADMIN-protected endpoint such as `/Marti/api/inputs`.
