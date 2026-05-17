/** Matches case_data.schema.json */

export interface CaseData {
  schema_version: string
  case: CaseMeta
  applicant: Applicant
  application: Application
  passport?: Passport
  residence_card?: ResidenceCard
  immigration_history?: ImmigrationHistory
  family?: Family
  education?: Education[]
  transcript_subjects?: TranscriptSubject[]
  employment_history?: EmploymentRecord[]
  qualifications?: Qualification[]
  employer?: Employer
  proxy?: Record<string, unknown>
  intermediary?: Record<string, unknown>
  receiving_method?: Record<string, unknown>
  supporting_documents?: SupportingDocument[]
  assessments?: Assessment[]
  field_metadata?: Record<string, unknown>
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
}

export interface Application {
  desired_status_label?: string
  purpose_of_entry?: string
  planned_entry_date?: string
  planned_port?: string
  planned_port_other?: string
  planned_period_years?: string
  planned_period_months?: string
  visa_application_location?: string
  activity_details?: string
  activity_details_structured?: {
    department?: string
    role?: string
    duties?: string[]
    simple_labor_risk_terms?: string[]
  }
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
}

export interface Family {
  has_accompanying_members?: boolean
  has_japan_relatives_or_cohabitants?: boolean
  japan_relatives_or_cohabitants?: Record<string, unknown>[]
}

export interface Education {
  school_name?: string
  major?: string
  graduation_date?: string
  source_refs?: string[]
}

export interface TranscriptSubject {
  name?: string
  matched_duty?: string
}

export interface EmploymentRecord {
  country_region?: string
  start_date?: string
  end_date?: string
  company_name_en?: string
  company_name_ja?: string
  duties?: string[]
  source_refs?: string[]
}

export interface Qualification {
  name?: string
  issuer?: string
  date?: string
}

export interface Employer {
  name?: string
  corporate_number?: string
  industry?: string
  capital_jpy?: number
  annual_sales_jpy?: number
  employee_count?: number
  branch_office?: string
  address?: string
  phone?: string
  representative_name?: string
  representative_title?: string
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
  case_data: CaseData
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
