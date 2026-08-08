# Seller Release Inputs

Complete this file with verified information before requesting the final signed
commercial build. Do not place passwords, private signing keys, contract text,
or API secrets in this repository.

## Seller identity

- Legal business/person name:
- Trading name:
- Registered business address:
- Country and sales regions:
- Company/registration number, if applicable:
- VAT/tax identifier, if applicable:
- Customer support email:
- Privacy contact email:
- Support hours and expected response time:

## Product terms

- Sales channel and checkout provider:
- Currency and price:
- License duration and number of permitted devices:
- Update policy and supported version period:
- Refund/cancellation policy approved for each sales region:
- Customer EULA/terms reviewed by:
- Privacy disclosure reviewed by:
- Review date and next review date:

## Rights evidence

- Upstream commercial license evidence location:
- JARVIS name/brand clearance reviewer and date:
- Logo/visual asset rights evidence:
- Voice identity and reference-audio rights evidence:
- NeuTTS/model commercial-use review:
- Any geographic or time restrictions:

## Distribution

- Public HTTPS download origin:
- Published SHA-256 checksum page:
- Update channel decision:
- Windows signing provider/certificate:
- Clean Windows 10 x64 test machine:
- Clean Windows 11 x64 test machine:

## Optional connected accounts

- Production Google Cloud project ID:
- OAuth consent screen published:
- Exact Gmail and Calendar scopes verified:
- Google brand/scope verification status:
- Real connect/read/disconnect test date:

## Machine-checkable release confirmations

The strict release audit passes only when every non-confidential confirmation
file contains all of these fields:

```text
Status: APPROVED
Reviewed by: Full name or responsible organisation
Review date: YYYY-MM-DD
Scope: JARVIS v4.1.2 Windows x64 commercial release
```

Add the exact decision line required for each file:

- `COMMERCIAL_LICENSE_CONFIRMATION.md`: `Commercial use permitted: YES`
- `BRAND_CLEARANCE_CONFIRMATION.md`: `Brand use cleared: YES`
- `VOICE_RIGHTS_CONFIRMATION.md`: `Commercial voice use permitted: YES`
- `PRIVACY_LEGAL_CONFIRMATION.md`: `Seller identity verified: YES`
- `WINDOWS_SIGNING_CONFIRMATION.md`: `Authenticode status: VALID`
- `RELEASE_QA_CONFIRMATION.md`: `Windows 10: PASS`, `Windows 11: PASS`,
  `Install: PASS`, `Upgrade: PASS`, `German microphone: PASS`,
  `English microphone: PASS`, and `Uninstall: PASS`

The signing and QA confirmations must additionally contain the SHA-256 of the
exact tested installer:

```text
Artifact SHA-256: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

Reference reviewed evidence without committing contracts, identity documents,
passwords, signing keys, API keys or other secrets to this repository.
