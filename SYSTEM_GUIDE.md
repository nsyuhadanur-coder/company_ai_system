# Nusantara Enterprise Solutions Sdn. Bhd.
## Malaysian Corporate Expense & Procurement ERP System (MYR / RM)

### 1. Corporate Entity & Localization Profile
- **Company Name**: Nusantara Enterprise Solutions Sdn. Bhd.
- **SSM Registration No**: `202401045892 (1542890-X)`
- **SST Registration No**: `W10-2401-32000088`
- **TIN (LHDN Tax ID)**: `C 25890123040`
- **Headquarters**: Level 28, The Horizon, Bangsar South City, No. 8, Jalan Kerinchi, 59200 Kuala Lumpur, Wilayah Persekutuan Kuala Lumpur, Malaysia
- **Base Currency**: Malaysian Ringgit (**MYR / RM**)
- **SST Rates**: `0%` (Zero-Rated / Exempt), `6%` (Standard Services), `8%` (Revised 2024 Scope)
- **Supported Financial Institutions**: Malayan Banking Berhad (Maybank), CIMB Bank Berhad, Public Bank Berhad, RHB Bank, Hong Leong Bank, AmBank, Bank Islam, DuitNow QR & Interbank GIRO (IBG).

---

### 2. Default Access Credentials

| Role | Account Name | Email | Password | Permissions |
|---|---|---|---|---|
| **Managing Director / Admin** | Dato' Farid Ibrahim | `admin@company.com` | `admin123` | Full ERP Control, Finance Sign-off, Bank Disbursements, System Config |
| **Finance Manager** | Sarah binti Tan Sri Azman | `manager@company.com` | `manager123` | Multi-tier Claims Review, PR Review, PO Approval, Invoice Verification |
| **Senior Staff / Employee** | Khairul bin Ahmad | `employee@company.com` | `employee123` | Submit Expense Claims, Raise Purchase Requests, View Personal History |

---

### 3. Core Modules & Key Features

#### A. Expense Submission & Claims Management
- **SST Computation**: Automatically handles `0%`, `6%`, and `8%` Malaysian Sales & Service Tax with tax-exclusive subtotal breakdown.
- **Payment Methods**: Cash reimbursement, Maybank Corporate Card, DuitNow QR, and IBG Bank Transfer.
- **Itemized Lines**: Option to attach single or multiple itemized receipt line items.
- **Receipt Archival**: File uploads supported for PDF, PNG, JPG, and JPEG.

#### B. Expense Categories & MYR Monthly Budgets
- Pre-loaded Malaysian corporate categories:
  - *Travel & Mileage (Perjalanan & Tol)*: RM 15,000 / month
  - *Meals & Entertainment (Keraian)*: RM 8,000 / month
  - *Office Supplies (Bekalan Pejabat)*: RM 5,000 / month
  - *IT & Software Licenses (Lesen Perisian)*: RM 25,000 / month
  - *Training & Professional Fees*: RM 12,000 / month
  - *Utilities & Telecommunications (Maxis/TM)*: RM 7,000 / month
- Real-time visual progress bars show budget utilization against the monthly allowance.

#### C. Multi-Tier Approval Workflow & Clarification Threads
- **Two-tier Approval Protocol**:
  1. **Line Manager Approval**: Validates business need and project allocation.
  2. **Finance Approval**: Audits tax invoices, receipts, and SST calculations.
- **Clarification Query System**: Approvers can request additional information; employees can respond in-line, transitioning claims between review states seamlessly.
- **Reimbursement Disbursement**: Records payment reference numbers and recipient bank accounts.

#### D. Purchase Request (PR) System
- Requisitions track department, priority levels (*Urgent*, *High*, *Normal*, *Low*), delivery due dates, and business justification.
- Line items support quantities, specifications, units of measure, and estimated unit prices in RM.
- Multi-tier approval before conversion into binding company commitments.

#### E. Purchase Orders (PO) with Malaysian Corporate Letterhead
- **1-Click Conversion**: Approved PRs can be converted into an official PO with a single click.
- **Official Malaysian Corporate Letterhead**: Displays Nusantara Enterprise Solutions Sdn. Bhd. registration details (SSM and SST IDs), vendor addresses, payment terms (Net 30, Cash on Delivery, etc.), and terms & conditions.
- **Printable Voucher**: Clean print CSS layout ready for physical signing or PDF export.

#### F. Supplier Invoices & 3-Way Matching (Accounts Payable)
- **Vendor Directory**: Pre-seeded with top Malaysian vendors (Dell Global Business Center Sdn. Bhd., Amazon Web Services Malaysia, Maxis Broadband, Pelikan, etc.) including SSM and bank details.
- **3-Way Matching**: Links Supplier Invoice to the issued PO and checks line totals, variance amounts, and SST charges:
  - `Matched`: Subtotal and tax match the PO within tolerance.
  - `Variance Detected`: Price or tax discrepancy flagged for review.
  - `Direct Non-PO`: Direct operational bills with department sign-off.
- **Malaysian Bank Disbursement**: Record payment release with Maybank, CIMB, or Public Bank transaction references.

---

### 4. Running the Application

Both servers can be started simultaneously using the preconfigured batch scripts:

```cmd
:: Quick Start (Launches Backend on :5000 and Frontend on :3000)
RUN.bat

:: Or Single-Port Unified Production Mode (serves both API and React Client on :5000)
START_STANDALONE.bat
```
