/**
 * The shapes the API speaks.
 *
 * Hand-written rather than generated, and that is a deliberate trade. FastAPI
 * publishes no `securitySchemes` (authentication lives in middleware, and the
 * guards take a bare `Request`), and Pydantic v2 splits every model into
 * `X-Input` and `X-Output` variants — so a generated client produces two types
 * per entity and no auth handling at all. These are the shapes the screens
 * actually read, written once, with that split collapsed.
 *
 * The `openapi-drift` CI job regenerates the schema and fails on a mismatch, so
 * "hand-written" does not mean "allowed to drift".
 */

/** What an account may do. */
export type UserRole = 'hca' | 'manager' | 'admin';

/** Where a quote sits in its lifecycle. */
export type QuoteStatus =
  'draft' | 'pending-validation' | 'sent' | 'accepted' | 'rejected' | 'expired';

/** Where a scheduled visit sits in its lifecycle. */
export type InterventionStatus = 'planned' | 'confirmed' | 'completed' | 'cancelled';

/** What an assistant is employed as. */
export type ContractType = 'cdi' | 'cdd' | 'interim' | 'internship';

/** Whether a customer is still served. */
export type RegistrationStatus = 'active' | 'stopped';

/** What a notification is about. */
export type NotificationKind =
  'quote-submitted' | 'quote-validated' | 'quote-refused' | 'planning-completed';

/** A signed-in account. */
export interface User {
  id: string | null;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  hca_id: string | null;
  company_id: string | null;
  must_change_password: boolean;
  created_at: string | null;
  updated_at: string | null;
}

/** The token a sign-in yields. */
export interface AccessToken {
  access_token: string;
  token_type: string;
  expires_in: number;
}

/** A postal address, with the outcome of geocoding it. */
export interface PostalAddress {
  street: string;
  postal_code: string;
  city: string;
  country: string;
  latitude: number | null;
  longitude: number | null;
  geocoding_error: string | null;
}

/** A qualification an assistant holds. */
export interface Certification {
  name: string;
  issuer: string | null;
  obtained_on: string | null;
  expires_on: string | null;
}

/** An assistant's driving licence. */
export interface DrivingLicense {
  categories: string[];
  number: string | null;
  obtained_on: string | null;
  expires_on: string | null;
}

/** A period an assistant cannot work. */
export interface AvailabilitySlot {
  id: string | null;
  hca_id: string;
  start_date: string;
  end_date: string;
  kind: string;
  start_time: string | null;
  end_time: string | null;
  note: string | null;
}

/** A home care assistant. */
export interface Hca {
  id: string | null;
  first_name: string;
  last_name: string;
  phone_number: string;
  email: string;
  address: PostalAddress;
  contract_type: ContractType;
  certifications: Certification[];
  driving_license: DrivingLicense | null;
  photo_url: string | null;
  availability: AvailabilitySlot[];
  created_at: string | null;
  updated_at: string | null;
}

/** Somebody the agency serves. */
export interface Customer {
  id: string | null;
  first_name: string;
  last_name: string;
  phone_number: string;
  email: string;
  address: PostalAddress;
  registration_status: RegistrationStatus;
  created_at: string | null;
  updated_at: string | null;
}

/** One service on a quote. */
export interface QuoteLine {
  id: string | null;
  name: string;
  intervention_type_id: string;
  /**
   * Which VAT rate this line is billed at.
   *
   * On the line rather than on the catalogue entry: the same service is
   * necessity care for one customer and comfort care for another, so it
   * depends on who is being quoted rather than on what is being sold.
   */
  service_category: 'necessity' | 'comfort';
  service_date: string;
  earliest_start: string;
  latest_end: string;
  duration_minutes: number;
  hourly_rate_ht: string | null;
  total_ht: string | null;
  vat_amount: string | null;
  total_ttc: string | null;
}

/** A quote's totals for one service type in one ISO week. */
export interface QuoteTypeWeekAggregate {
  intervention_type_id: string;
  intervention_type_name: string;
  iso_year: number;
  iso_week: number;
  week_start_date: string;
  line_count: number;
  total_minutes: number;
  total_ht: string;
  vat_amount: string;
  total_ttc: string;
}

/** A priced offer of home care. */
export interface Quote {
  id: string | null;
  reference: string;
  customer_id: string;
  status: QuoteStatus;
  lines: QuoteLine[];
  aggregates: QuoteTypeWeekAggregate[];
  issued_on: string | null;
  valid_until: string | null;
  authored_by: string | null;
  submitted_at: string | null;
  validated_by: string | null;
  validated_at: string | null;
}

/** An entry in the service catalog. */
export interface InterventionType {
  id: string | null;
  name: string;
  code: string;
  description: string | null;
  service_category: 'necessity' | 'comfort';
  base_hourly_rate_ht: string | null;
  is_active: boolean;
}

/** One scheduled visit. */
export interface Intervention {
  id: string | null;
  planning_run_id: string | null;
  name: string;
  intervention_type_id: string;
  quote_line_id: string;
  hca_id: string;
  hca_full_name: string;
  customer_id: string;
  day: string;
  start_time: string;
  end_time: string;
  address: PostalAddress;
  status: InterventionStatus;
}

/** One assistant's diary over a period. */
export interface HcaPlanning {
  hca_id: string;
  hca_full_name: string;
  period_start: string;
  period_end: string;
  interventions: Intervention[];
}

/** Something that happened, addressed to one account. */
export interface Notification {
  id: string | null;
  recipient_id: string;
  kind: NotificationKind;
  title: string;
  body: string | null;
  quote_id: string | null;
  is_read: boolean;
  created_at: string | null;
  read_at: string | null;
}

/** One execution of the planning computation. */
export interface PlanningRun {
  id: string | null;
  status: 'pending' | 'running' | 'succeeded' | 'failed';
  requested_by: string;
  period_start: string;
  period_end: string;
  started_at: string | null;
  finished_at: string | null;
  total_travel_minutes: number | null;
  scheduled_count: number | null;
  unassigned_requirement_ids: string[];
  error_message: string | null;
}

/** An agency. */
export interface Company {
  /** Identifier. */
  id: string;
  /** Trading name. */
  name: string;
  /** Registration number, when the agency has been issued one. */
  registration_number: string | null;
  /** Contact address. */
  contact_email: string | null;
  /** Registered address, when one has been recorded. */
  address: PostalAddress | null;
  /** Whether assistants may currently apply. */
  is_accepting_applications: boolean;
  /** When the agency was founded in this system. */
  created_at?: string | null;
  /** When its details were last changed. */
  updated_at?: string | null;
}

/**
 * What an administrator may change about their own agency.
 *
 * Deliberately narrower than `Company`: no identifier, no timestamps. The
 * server's payload model carries the same fields and no others, so the two
 * agree by construction rather than by anybody remembering to keep them so.
 */
export interface CompanyProfileUpdate {
  name: string;
  registration_number: string | null;
  contact_email: string | null;
  address: PostalAddress | null;
  is_accepting_applications: boolean;
}

/**
 * What a manager may change about a catalogue entry.
 *
 * `code` is absent: it is the stable key stored on every quote line ever
 * written against the type, and changing it would orphan them.
 */
export interface InterventionTypeUpdate {
  name?: string;
  description?: string | null;
  service_category?: 'necessity' | 'comfort';
  base_hourly_rate_ht?: string | null;
  is_active?: boolean;
}

/** The agency-wide rules a catalogue entry is priced against. */
export interface PricingRules {
  base_hourly_rate_ht: string;
  weekday_surcharges: Record<string, string>;
  holiday_surcharges: {
    month: number;
    day: number;
    surcharge: string;
    label: string;
  }[];
  vat_rates: Record<string, string>;
}

/** What founding an agency asks for. */
export interface CompanyRegistrationRequest {
  /** The agency's trading name. */
  company_name: string;
  /** The agency's registration number, if it has one yet. */
  registration_number?: string | null;
  /** The founder's display name. */
  full_name: string;
  /** The founder's sign-in address. */
  email: string;
  /** The founder's chosen password. */
  password: string;
}

/**
 * What founding an agency hands back.
 *
 * @remarks
 * No token: the founder signs in through the ordinary route with the password
 * they just chose, so there is one place that mints credentials rather than
 * two.
 */
export interface CompanyRegistrationResponse {
  /** The agency that was created. */
  company: Company;
  /** The founder's account, without its password hash. */
  administrator: User;
}

/** A line on a quote being created, before the server prices it. */
export interface NewQuoteLine {
  /** What the line is called on the document. */
  name: string;
  /** The catalogue entry it bills against. */
  intervention_type_id: string;
  /** Which VAT rate it is billed at; decided per customer, not per service. */
  service_category: 'necessity' | 'comfort';
  /** The day the visit happens. */
  service_date: string;
  /** Earliest the visit may start. */
  earliest_start: string;
  /** Latest it may end. */
  latest_end: string;
  /** How long it takes. */
  duration_minutes: number;
}

/**
 * A quote being created.
 *
 * @remarks
 * Carries no amounts. The server prices every line against the catalogue as it
 * stands, so a total computed in the browser would be a second answer that can
 * disagree with the stored one.
 */
export interface NewQuote {
  /** The human-facing quote number. */
  reference: string;
  /** Who it is addressed to. */
  customer_id: string;
  /** The services offered. */
  lines: NewQuoteLine[];
}
