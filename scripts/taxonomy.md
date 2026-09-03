# Classification taxonomy

Every parsed email is classified into exactly one of the categories below.
This file is the single source of truth for the taxonomy - `classify_emails.py`
loads it directly into the classification prompt, so edit here rather than
duplicating category definitions in code.

| category | definition |
|---|---|
| `borrower_decline` | Declining, rejecting, or pushing back on a borrower request (extension, waiver, consent, lease approval, etc.) |
| `borrower_approval` | Approving or granting a borrower request |
| `ire_recommendation` | A recommendation made to IRE/INCREF on a course of action (e.g. "we recommend approving...", "our recommendation is to decline...") |
| `ire_news_positive` | Significant good news delivered to IRE (e.g. loan payoff, NOI outperformance, successful lease-up, covenant cure) |
| `ire_news_negative` | Significant bad news delivered to IRE (e.g. DY/covenant breach, occupancy decline, borrower default risk, litigation) |
| `covenant_dy_issue` | Debt yield or other covenant breach, cure, or compliance-test communication |
| `modification_waiver` | Loan modification, waiver, or forbearance decision or discussion |
| `none` | Routine, administrative, or purely informational - not a candidate for the writing-style training set |

## Guidance for the classifier

- An email can plausibly fit more than one category (e.g. a covenant breach that
  is also negative IRE news). Pick the single category that best captures the
  *primary purpose* of the email.
- Only classify emails that represent the asset manager's own analysis,
  decision, or communication of a decision - not emails that merely forward or
  quote someone else's decision without added judgment.
- Calendar invites, out-of-office replies, meeting logistics, and pure
  document-transmittal emails ("attached please find...") are always `none`.
- Standard reserve/CapEx draw request processing (submitting, approving, or
  funding a routine draw request under the loan documents) is always `none` -
  this is standard process and does not carry useful writing-style context.
  Only classify a draw-related email outside `none` if it reflects a
  substantive decision beyond routine processing (e.g. declining a draw due
  to a covenant or documentation issue, which is `borrower_decline` or
  `covenant_dy_issue` as appropriate).
- When uncertain, prefer the more specific category over `none`.
