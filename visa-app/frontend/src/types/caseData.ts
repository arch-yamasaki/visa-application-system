/** Matches case_data.schema.json */

export interface CaseData {
  schema_version: string
  case: CaseMeta
  applicant: Applicant
  entry_plan?: EntryPlan
  transcript_subjects?: TranscriptSubject[]
  employer?: Employer
  employment?: Employment
  proxy?: Proxy
  receiving_method?: ReceivingMethod
  settings?: Settings
  supporting_documents?: SupportingDocument[]
  assessments?: Assessment[]
}

export interface CaseMeta {
  case_id: string
  intake_channel?: string
  source_organization?: string
  application_type: string
  target_status: string
  workflow_state: string
  routed_to_human_reason?: string[]
}

export interface Applicant {
  nationality_region?: string
  birth_date?: string
  name_roman?: string
  name_kanji?: string
  sex?: string
  birth_place?: string
  marital_status?: string
  occupation?: string
  home_country_address?: string
  japan_contact?: {
    postal_code?: string
    address?: string
    phone?: string
    mobile?: string
    email?: string
  }
  passport?: Passport
  residence_card?: ResidenceCard
  immigration_history?: ImmigrationHistory
  family?: Family
  education?: Education[]
  has_employment_history?: boolean
  employment_history?: EmploymentRecord[]
  qualifications?: Qualifications
}

export interface EntryPlan {
  main_activity_category?: string
  purpose_of_entry?: string
  planned_entry_date?: string
  planned_port?: string
  planned_port_other?: string
  planned_period_years?: string
  planned_period_months?: string
  visa_application_location?: string
  previous_denial_reason?: string
  amendment_history?: unknown[]
}

export interface Passport {
  number?: string
  expiry_date?: string
}

export interface ResidenceCard {
  number?: string
  status?: string
  expiry_date?: string
}

export interface ImmigrationHistory {
  has_entries?: boolean
  entries_count?: number | string
  latest_entry?: {
    start_date?: string
    end_date?: string
  }
  prior_coe_applications?: {
    has_history?: boolean
    count?: number | string
    denial_count?: number | string
  }
  criminal_record?: boolean
  deportation_or_departure_order?: boolean
  deportation_count?: number | string
  deportation_latest?: string
}

export interface Family {
  has_accompanying_members?: boolean
  has_japan_relatives_or_cohabitants?: boolean
  japan_relatives_or_cohabitants?: JapanRelativeOrCohabitant[]
}

export interface JapanRelativeOrCohabitant {
  relationship?: string
  name?: string
  birth_date?: string
  nationality_region?: string
  will_cohabit?: boolean
  workplace_or_school_name?: string
  residence_card_or_certificate_number?: string
}

export interface Education {
  country_type?: string
  level?: string
  level_detail?: string
  level_other?: string
  school_name?: string
  major_field?: string
  major_field_other?: string
  graduation_date?: string
  source_refs?: string[]
}

export interface TranscriptSubject {
  name?: string
  matched_duty?: string
}

export interface EmploymentRecord {
  country_region?: string
  start_month_unknown?: boolean
  start_date?: string
  end_month_unknown?: boolean
  end_date?: string
  company_name_en?: string
  company_name_local?: string
  duties?: string[]
  source_refs?: string[]
}

export interface Qualification {
  type?: string
  name?: string
  level?: string
  issuer?: string
  issue_date?: string
}

export interface Qualifications {
  it?: {
    has_qualification?: boolean
    qualification_name?: string
  }
  items?: Qualification[]
}

export interface Employer {
  name?: string
  has_corporate_number?: boolean
  corporate_number?: string
  postal_code?: string
  office_name?: string
  employment_insurance_office_number?: string
  industry_primary?: string
  industry_other?: string
  industry?: string
  capital_jpy?: number
  annual_sales_jpy?: number
  employee_count?: number
  foreign_employee_count?: number
  technical_intern_count?: number
  branch_office?: string
  address?: string
  phone?: string
  representative_name?: string
  representative_title?: string
}

export interface Employment {
  contract_type?: string
  employment_period_type?: string
  employment_period_years?: string
  employment_period_months?: string
  joining_date?: string
  monthly_salary?: number | string
  experience_months?: number | string
  has_position?: boolean
  position_title?: string
  job_category_primary?: string
  activity_details?: string
  work_location?: string
}

export interface Proxy {
  name?: string
  relationship?: string
  postal_code?: string
  address?: string
  phone?: string
  mobile?: string
}

export interface ReceivingMethod {
  method?: string
  postal_code?: string
  address?: string
}

export interface Settings {
  intermediary?: Intermediary
}

export interface Intermediary {
  organization?: string
  name?: string
  postal_code?: string
  address?: string
  phone?: string
}

export interface SupportingDocument {
  document_type?: string
  file_name?: string
  notes?: string
}

export interface Assessment {
  type: string
  status: string
  summary: string
}

// --- Document Manifest ---

export interface DocumentEntry {
  document_id: string
  document_role: string
  file_name: string
  gcs_path: string
  extension?: string
  page_count?: number
  uploaded_at?: string
}

export interface DocumentManifest {
  documents: DocumentEntry[]
}

// --- Field Metadata ---

export interface SourceRef {
  document_id: string
  page: number
  text_quote: string
  confidence: number
  bbox?: { y_min: number; x_min: number; y_max: number; x_max: number }
}

export interface FieldMeta {
  source_refs: SourceRef[]
  human_reviewed?: boolean
  human_edited?: boolean
  original_value?: string
}

export type FieldMetadataMap = Record<string, FieldMeta>

// --- Review ---

export interface ReviewItem {
  path: string
  reason: string
  evidence_refs?: string[]
}

export interface Finding {
  code: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  message: string
  evidence_refs?: string[]
}

export interface ReviewAssessment {
  type: string
  status: string
  summary: string
}

export interface Review {
  schema_version?: string
  case_id?: string
  expected_route?: 'ok' | 'needs_review' | 'needs_information' | 'human_required'
  missing_documents?: ReviewItem[]
  missing_items?: ReviewItem[]
  validation_errors?: ReviewItem[]
  findings?: Finding[]
  assessments?: ReviewAssessment[]
}

// --- Case Document (full Firestore document) ---

export interface CaseDocument {
  case_id: string
  workflow_state: string
  created_at: string
  updated_at: string
  settings?: Settings
  case_data: CaseData
  canonical_case_data?: CaseData
  field_metadata: FieldMetadataMap
  review: Review
  document_manifest: DocumentManifest
  extraction_session_id?: string | null
  confirmed_at?: string | null
  applicant_name_preview?: string
}

export interface CaseSummary {
  case_id: string
  workflow_state: string
  created_at: string
  applicant_name_preview?: string
}
