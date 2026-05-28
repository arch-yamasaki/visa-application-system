import type {
  CaseDocument,
  CaseSummary,
  DocumentEntry,
  FieldMetadataMap,
  Review,
} from '../types/caseData'

// Inlined from rasens-autofill/data/cases/demo_case_data.json
const demoCaseData = {
  schema_version: '1.0',
  case: {
    case_id: 'demo-gijinkoku-001',
    intake_channel: 'recruiting_agency',
    source_organization: 'Demo Recruiting Agency',
    application_type: 'certificate_of_eligibility',
    target_status: 'engineer_humanities_international',
    workflow_state: 'extracted',
    routed_to_human_reason: [],
  },
  entry_plan: {
    main_activity_category: '技術・人文知識・国際業務',
    purpose_of_entry: '技術・人文知識・国際業務',
    planned_entry_date: '2026-08-01',
    planned_port: '関西国際空港',
    planned_period_years: '5',
    planned_period_months: '0',
    visa_application_location: 'ハノイ',
  },
  applicant: {
    nationality_region: 'ベトナム Viet Nam',
    birth_date: '2000-04-15',
    name_roman: 'NGUYEN VAN DEMO',
    name_kanji: '',
    sex: 'male',
    birth_place: 'HANOI',
    marital_status: 'single',
    occupation: '会社員',
    home_country_address: 'Hanoi, Viet Nam',
    japan_contact: {
      postal_code: '5300001',
      address: '大阪府大阪市北区梅田1-1-1',
      phone: '0660000000',
      mobile: '09000000000',
      email: 'demo.applicant@example.com',
    },
    passport: {
      number: 'P0000000',
      expiry_date: '2030-04-14',
    },
    residence_card: {
      number: '',
      status: '',
      expiry_date: '',
    },
    family: {
      has_accompanying_members: false,
      has_japan_relatives_or_cohabitants: false,
      japan_relatives_or_cohabitants: [],
    },
    immigration_history: {
      has_entries: true,
      entries_count: 1,
      latest_entry: {
        start_date: '2024-06-01',
        end_date: '2024-06-10',
      },
      prior_coe_applications: {
        has_history: false,
        count: 0,
        denial_count: 0,
      },
      criminal_record: false,
      deportation_or_departure_order: false,
    },
    education: [
      {
        id: 'edu_01',
        level: 'university',
        school_name: 'Demo University of Technology',
        major_field: 'Mechanical Engineering',
        graduation_date: '2023-03-31',
        source_refs: ['demo_transcript.pdf#p1'],
      },
    ],
    employment_history: [
      {
        id: 'emp_01',
        country_region: 'ベトナム Viet Nam',
        start_date: '2023-04',
        end_date: '2026-03',
        company_name_en: 'Demo Engineering Co., Ltd.',
        company_name_local: 'Demo Engineering Co., Ltd.',
        duties: ['製造設備の設計補助', '品質管理資料作成'],
      },
    ],
    qualifications: {
      it: {
        has_qualification: false,
        qualification_name: '',
      },
      items: [
        {
          type: 'language',
          name: 'JLPT',
          level: 'N2',
          issue_date: '2025-01-31',
        },
      ],
    },
  },
  transcript_subjects: [
    { name: 'Control Engineering', matched_duty: '制御設計補助' },
    { name: 'Quality Management', matched_duty: '品質管理' },
  ],
  employer: {
    name: 'デモテクノロジー株式会社',
    corporate_number: '1234567890123',
    office_name: '大阪本社',
    employment_insurance_office_number: '2700-000000-0',
    industry_primary: '製造業',
    postal_code: '5300001',
    address: '大阪府大阪市北区梅田1-1-1',
    phone: '0660000000',
    capital_jpy: 10000000,
    annual_sales_jpy: 250000000,
    employee_count: 80,
    foreign_employee_count: 8,
    technical_intern_count: 0,
    category: 'category_3',
  },
  employment: {
    contract_type: '雇用 Employment',
    monthly_salary: 300000,
    job_category_primary: '技術開発',
    activity_details:
      '技術総合職として、製造設備の制御設計、品質管理、工程改善に関する資料作成及び海外拠点との技術連絡業務に従事します。',
  },
  proxy: {
    name: 'デモ 太郎',
    relationship: '取次者',
    postal_code: '5300001',
    address: '大阪府大阪市北区梅田1-1-1',
    phone: '0660000000',
    mobile: '09000000000',
  },
  supporting_documents: [
    { document_type: 'passport', status: 'received', source: 'demo_passport.pdf' },
    { document_type: 'resume', status: 'received', source: 'demo_resume.pdf' },
    { document_type: 'graduation_certificate', status: 'received', source: 'demo_graduation.pdf' },
    { document_type: 'transcript', status: 'received', source: 'demo_transcript.pdf' },
    { document_type: 'employment_contract', status: 'received', source: 'demo_employment_contract.pdf' },
  ],
  assessments: [
    {
      type: 'gijinkoku_fit',
      status: 'ok',
      summary: '専攻科目と活動内容の対応があり、単純労働リスク語は検出されていない。',
    },
  ],
}

// --- Generate field_metadata with source refs ---

function generateFieldMetadata(): FieldMetadataMap {
  const fields: Record<string, { confidence: number; quote: string }> = {
    'applicant.nationality_region': { confidence: 0.97, quote: 'ベトナム Viet Nam' },
    'applicant.birth_date': { confidence: 0.96, quote: '2000-04-15' },
    'applicant.name_roman': { confidence: 0.98, quote: 'NGUYEN VAN DEMO' },
    'applicant.sex': { confidence: 0.95, quote: 'male' },
    'applicant.birth_place': { confidence: 0.93, quote: 'HANOI' },
    'applicant.passport.number': { confidence: 0.97, quote: 'P0000000' },
    'applicant.passport.expiry_date': { confidence: 0.96, quote: '2030-04-14' },
    'applicant.japan_contact.postal_code': { confidence: 0.91, quote: '5300001' },
    'applicant.japan_contact.address': { confidence: 0.90, quote: '大阪府大阪市北区梅田1-1-1' },
    'applicant.japan_contact.phone': { confidence: 0.88, quote: '0660000000' },
    'applicant.japan_contact.mobile': { confidence: 0.87, quote: '09000000000' },
    'applicant.japan_contact.email': { confidence: 0.92, quote: 'demo.applicant@example.com' },
    'entry_plan.main_activity_category': { confidence: 0.95, quote: '技術・人文知識・国際業務' },
    'entry_plan.planned_entry_date': { confidence: 0.94, quote: '2026-08-01' },
    'entry_plan.planned_port': { confidence: 0.89, quote: '関西国際空港' },
    'employment.activity_details': { confidence: 0.86, quote: '技術総合職として…' },
    'employer.name': { confidence: 0.97, quote: 'デモテクノロジー株式会社' },
    'employer.address': { confidence: 0.93, quote: '大阪府大阪市北区梅田1-1-1' },
    'employer.phone': { confidence: 0.91, quote: '0660000000' },
  }

  const result: FieldMetadataMap = {}
  for (const [path, { confidence, quote }] of Object.entries(fields)) {
    result[path] = {
      source_refs: [
        {
          document_id: 'doc_001',
          page: 1,
          text_quote: quote,
          confidence,
        },
      ],
      human_reviewed: false,
      human_edited: false,
    }
  }
  return result
}

// --- Mock review ---

const demoReview: Review = {
  schema_version: '1.0',
  case_id: 'demo-gijinkoku-001',
  expected_route: 'needs_review',
  missing_documents: [],
  missing_items: [
    {
      path: 'applicant.name_kanji',
      reason: '漢字氏名が未入力です。旅券に漢字氏名の記載がある場合は転記してください。',
    },
    {
      path: 'employer.capital_jpy',
      reason: '資本金の金額が入力されていますが、根拠書類との照合が必要です。',
    },
    {
      path: 'applicant.home_country_address',
      reason: '本国住所の詳細（番地・通り名）が不足しています。',
    },
  ],
  validation_errors: [],
  findings: [
    {
      code: 'ACTIVITY_BROAD',
      severity: 'medium',
      message:
        '活動内容詳細の記述が広範囲です。具体的な業務内容を絞り込んでください。',
    },
    {
      code: 'EDUCATION_MATCH_PARTIAL',
      severity: 'low',
      message:
        '専攻科目 (Mechanical Engineering) と業務 (制御設計補助) の対応は部分的です。',
    },
  ],
  assessments: [
    {
      type: 'gijinkoku_fit',
      status: 'ok',
      summary: '専攻科目と活動内容の対応があり、単純労働リスク語は検出されていない。',
    },
  ],
}

// --- Mock document manifest ---

const demoDocuments: DocumentEntry[] = [
  {
    document_id: 'doc_001',
    document_role: 'passport',
    file_name: 'passport.pdf',
    gcs_path: 'demo/passport.pdf',
    extension: 'pdf',
    page_count: 2,
    uploaded_at: '2026-05-10T10:00:00Z',
  },
  {
    document_id: 'doc_002',
    document_role: 'resume',
    file_name: 'resume.pdf',
    gcs_path: 'demo/resume.pdf',
    extension: 'pdf',
    page_count: 3,
    uploaded_at: '2026-05-10T10:01:00Z',
  },
]

// --- Exported mock helpers ---

const DEMO_CASE_ID = 'demo-gijinkoku-001'

const demoCaseDocument: CaseDocument = {
  case_id: DEMO_CASE_ID,
  workflow_state: 'extracted',
  created_at: '2026-05-10T09:00:00Z',
  updated_at: '2026-05-10T12:00:00Z',
  case_data: demoCaseData as CaseDocument['case_data'],
  field_metadata: generateFieldMetadata(),
  review: demoReview,
  document_manifest: { documents: demoDocuments },
  applicant_name_preview: 'NGUYEN VAN DEMO',
}

const demoCaseSummary: CaseSummary = {
  case_id: DEMO_CASE_ID,
  display_name: 'NGUYEN VAN DEMO / デモテクノロジー株式会社',
  applicant_name: 'NGUYEN VAN DEMO',
  employer_name: 'デモテクノロジー株式会社',
  target_status: 'engineer_humanities_international',
  application_type: 'certificate_of_eligibility',
  workflow_state: 'extracted',
  created_at: '2026-05-10T09:00:00Z',
  updated_at: '2026-05-10T12:00:00Z',
  applicant_name_preview: 'NGUYEN VAN DEMO',
}

// Public PDF sample for document viewer in demo mode
const SAMPLE_PDF_URL =
  'https://mozilla.github.io/pdf.js/web/compressed.tracemonkey-pldi-09.pdf'

export const mockApi = {
  listCases(): Promise<CaseSummary[]> {
    return Promise.resolve([demoCaseSummary])
  },

  getCase(_caseId: string): Promise<CaseDocument> {
    return Promise.resolve(structuredClone(demoCaseDocument))
  },

  updateCase(
    _caseId: string,
    updates: { case_data?: unknown; field_metadata?: unknown; workflow_state?: string },
  ): Promise<CaseDocument> {
    const updated = structuredClone(demoCaseDocument)
    if (updates.workflow_state) updated.workflow_state = updates.workflow_state
    return Promise.resolve(updated)
  },

  listDocuments(_caseId: string): Promise<DocumentEntry[]> {
    return Promise.resolve([...demoDocuments])
  },

  getDocumentUrl(
    _caseId: string,
    _documentId: string,
  ): Promise<{ signed_url: string }> {
    return Promise.resolve({ signed_url: SAMPLE_PDF_URL })
  },

  getDocumentSheets(
    _caseId: string,
    _documentId: string,
  ): Promise<{ sheets: string[] }> {
    return Promise.resolve({ sheets: [] })
  },

  createCase(_params: {
    application_type: string
    target_status: string
  }): Promise<{ case_id: string; workflow_state: string; created_at: string }> {
    return Promise.resolve({
      case_id: DEMO_CASE_ID,
      workflow_state: 'extracted',
      created_at: '2026-05-10T09:00:00Z',
    })
  },

  async uploadDocument(
    _caseId: string,
    _file: File,
    _role?: string,
  ): Promise<DocumentEntry> {
    return demoDocuments[0]
  },

  startExtraction(_caseId: string) {
    return Promise.resolve({ session_id: 'demo-session', status: 'completed' as string, error: undefined as string | undefined })
  },

  getExtractionStatus(_caseId: string) {
    return Promise.resolve({ status: 'completed', session_id: 'demo-session' as string | undefined })
  },
}
