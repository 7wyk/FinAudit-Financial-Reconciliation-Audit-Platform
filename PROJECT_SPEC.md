# FinAudit — Financial Reconciliation & Audit Platform

## 1. Purpose

FinAudit is an enterprise-style financial reconciliation and audit platform for comparing financial records from systems such as ERP/accounting systems and bank statements.

Core workflow:

`ERP / Bank Data → File Upload → Validation → Normalization → Deterministic Reconciliation → Matched / Unmatched / Conflict / Exception → Human Review → Approval / Resolution → Audit Trail → Reports`

AI is a supporting feature only. It is never the authoritative decision-maker.

---

## 2. Technology

### Backend
- Python
- Django
- Django REST Framework
- PostgreSQL
- Celery
- Redis
- JWT authentication
- pandas
- openpyxl

### Frontend
- React
- Vite
- TypeScript
- Tailwind CSS

### Development
- Docker
- Docker Compose
- Git
- GitHub

### Testing
- pytest
- pytest-django

### Production
- Backend: Render
- Frontend: Vercel
- PostgreSQL: Supabase
- File storage: Supabase Storage
- Redis: Upstash
- AI: Groq or OpenRouter
- CI/CD: GitHub Actions

React/Vite must remain the frontend architecture. Do not introduce Next.js or SSR.

---

## 3. Multi-Tenancy

Organizations must be completely isolated.

A user must never be able to access another organization's:
- users
- transactions
- files
- imports
- reconciliation runs
- exceptions
- rules
- reports
- audit records
- AI investigation data

Tenant isolation must be enforced server-side through Django/DRF permissions, query scoping, service-layer checks, and tests. Frontend filtering is never sufficient.

---

## 4. Authentication and RBAC

Use secure password handling and JWT authentication.

Roles:
- `ADMIN`
- `FINANCE_MANAGER`
- `RECONCILIATION_ANALYST`
- `AUDITOR`

Authorization must be enforced by Django/DRF, not only React.

Permissions should follow least privilege and be tested at API boundaries.

---

## 5. File Ingestion

Supported formats:
- CSV
- XLSX

Pipeline:

`Upload → Validate → Supabase Storage → Import Record → Celery → Parse → Validate → Normalize → Persist`

Track appropriate metadata including:
- filename
- source
- checksum
- file size
- uploader
- timestamp
- processing status
- row counts
- rejected rows
- processing/validation errors

Large or time-consuming processing must be asynchronous.

Validate files safely. Do not trust filenames, MIME types, extensions, uploaded content, or client-supplied metadata.

---

## 6. Canonical Transaction Model

Normalize heterogeneous source records into a common representation containing appropriate fields such as:
- external ID
- transaction date
- amount
- currency
- reference
- description
- counterparty
- source

Money must use `Decimal`.

The canonical model should preserve enough source/provenance information for investigation and auditability.

---

## 7. Deterministic Reconciliation

This is the core domain capability.

Support:
- exact reference matching
- normalized-reference matching
- amount tolerance
- date tolerance
- counterparty normalization
- controlled similarity
- deterministic scoring
- candidate generation
- ambiguous candidates
- conflicting candidates
- unmatched transactions

Rules:
- identical inputs must always produce identical results
- no random or nondeterministic decisions
- financial calculations use `Decimal`
- matching logic must be independent from HTTP/Django views
- matching logic must be directly unit-testable
- every candidate/result should expose explanation/evidence metadata
- similarity must be controlled and bounded; it must not silently override deterministic business rules

The reconciliation engine should be designed as a domain/service component rather than embedded in views or serializers.

---

## 8. Reconciliation States

Use explicit states including:
- `UNMATCHED`
- `CANDIDATE`
- `MATCHED`
- `PARTIALLY_MATCHED`
- `CONFLICT`
- `EXCEPTION`
- `UNDER_REVIEW`
- `RESOLVED`
- `REJECTED`

State transitions must be explicit and invalid transitions must be prevented.

State changes must be auditable.

---

## 9. Human Review

Reviewers must be able to:
- inspect transactions
- inspect candidate matches
- view matching evidence
- approve
- reject
- resolve exceptions
- add notes

Review actions must respect RBAC and tenant boundaries.

---

## 10. Audit Trail

Audit important events including:
- uploads
- reconciliation runs
- rule changes
- approvals
- rejections
- exception resolution
- user/role changes
- report generation

Audit records should include appropriate:
- organization
- user
- action
- entity
- timestamp
- previous state
- new state
- metadata

Audit records should be append-oriented and protected from unauthorized modification.

---

## 11. Reporting

Generate:
- reconciliation summaries
- matched transaction reports
- unmatched transaction reports
- exception reports
- import validation reports

Formats:
- CSV
- XLSX
- PDF where practical

Large reports should be generated asynchronously.

Report access must respect organization and role permissions.

---

## 12. Reconciliation Investigation Assistant

Implement a small AI feature named **Reconciliation Investigation Assistant**.

It may:
- explain why a transaction was not matched
- summarize reconciliation runs
- explain mismatch patterns
- suggest possible causes
- summarize existing reconciliation evidence

It must never:
- approve transactions
- modify financial records
- override deterministic rules
- bypass permissions

Use Groq or OpenRouter behind an AI service abstraction so the provider can be replaced.

AI credentials remain server-side.

AI must not be required for normal reconciliation.

AI output must be treated as explanatory/supporting information, not financial truth.

---

## 13. Frontend

The UI should take visual inspiration from the supplied Dribbble references without copying them pixel-for-pixel.

Design direction:
- enterprise financial software
- professional
- modern
- data-dense
- clean
- operational
- polished

Avoid:
- generic AI-generated dashboard appearance
- excessive gradients
- glassmorphism
- neon colors
- excessive rounded cards
- generic purple/blue AI styling
- unnecessary decoration

Required screens:
- Login
- Dashboard
- Imports
- Import Details
- Transactions
- Transaction Details
- Reconciliation Runs
- Exceptions
- Exception Investigation
- AI Investigation Assistant
- Rules
- Reports
- Audit Logs
- User Management

---

## 14. Accessibility

Where applicable:
- meaningful alt text
- semantic HTML
- keyboard accessibility
- accessible forms
- appropriate ARIA
- visible and understandable validation/error states
- usable focus states

Accessibility applies to the actual application UI, not as a reason to add unrelated features.

---

## 15. Performance

Use appropriate:
- modern image formats such as WebP where images exist
- lazy loading where useful
- optimized assets
- route/code splitting where useful
- efficient API queries
- pagination for large datasets
- asynchronous processing for expensive jobs

Do not optimize prematurely at the expense of maintainability.

---

## 16. Error Handling

Provide professional:
- API error handling
- validation errors
- loading states
- empty states
- processing states
- failure states
- custom 404 page
- appropriate application error states

Do not expose secrets, stack traces, or sensitive internals to end users.

---

## 17. Public Website / SEO

Separate authenticated application requirements from public website requirements.

If FinAudit has public-facing pages such as a landing page, documentation, about, or contact page, implement where applicable:
- unique page titles
- meta descriptions
- Open Graph metadata
- robots.txt
- sitemap.xml
- canonical URLs
- useful internal linking
- breadcrumbs where useful
- privacy policy
- working contact form
- 301 redirects where required

Do not add unnecessary SEO machinery to authenticated dashboard pages.

Do not introduce SSR or Next.js.

If a future public marketing site needs stronger SEO, it can be handled separately while retaining the React/Vite application architecture.

### Analytics
If implemented:
- use a privacy-conscious approach
- make it configurable through environment variables
- Google Analytics may be used for the public website
- analytics is not required for the authenticated dashboard

### Search Console
Google Search Console is an external deployment/configuration step. Document it; do not build unnecessary application functionality for it.

### Organization structured data
Only implement Organization schema if a public FinAudit/company landing page actually exists.

---

## 18. API and Architecture

Use clear separation between:
- API/presentation
- serializers/validation
- application services
- domain/reconciliation logic
- persistence
- background jobs
- external integrations

Keep business-critical reconciliation logic independent from HTTP concerns.

Build REST APIs using appropriate Django REST Framework conventions.

Avoid unnecessary abstraction and premature microservices.

---

## 19. Testing

Use pytest and pytest-django.

Tests should cover, as appropriate:
- authentication
- authorization
- tenant isolation
- API behavior
- models
- validation
- imports
- CSV/XLSX parsing
- normalization
- reconciliation rules
- deterministic scoring
- candidate handling
- state transitions
- human review
- audit logging
- reports
- AI permission boundaries
- security-sensitive behavior

The reconciliation engine requires comprehensive deterministic unit tests.

---

## 20. Deployment

Target:
- Backend: Render
- Frontend: Vercel
- PostgreSQL: Supabase
- Storage: Supabase Storage
- Redis: Upstash
- AI: Groq or OpenRouter
- CI/CD: GitHub Actions

Use environment variables for secrets and environment-specific configuration.

Never commit credentials.

Production configuration must distinguish development/test/production behavior.

Include production smoke tests and deployment documentation.

---

## 21. Security

Review:
- JWT authentication
- authorization
- tenant isolation
- password handling
- file upload security
- secrets
- CORS
- CSRF where applicable
- API permissions
- input validation
- unsafe file processing
- sensitive error leakage
- dependency/security configuration

Financial records must not be exposed through insecure object references or insufficiently scoped queries.

---

## 22. Git and Development Workflow

Develop incrementally.

Recommended loop:

`Claude → implement one phase → tests → review → Git commit → Codex → debug/test/review → Git commit → next phase`

Never rebuild the entire project in one context.

Never ask Codex to reconstruct the entire project.

Preserve working functionality between phases.

---

## 23. Stable Product Scope

The implementation should prioritize:
1. secure multi-tenant financial data handling
2. deterministic reconciliation
3. auditability
4. human review
5. reliable ingestion
6. enterprise workflow
7. usable data-dense UI
8. testing and deployment
9. supporting AI capabilities

AI must remain secondary to deterministic reconciliation.