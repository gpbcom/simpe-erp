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

/**
 * Where a customer stands with the agency.
 *
 * `prospect` is what a newly registered household is. They may be quoted —
 * that is what a prospect is *for* — but no planning run will schedule their
 * work until a manager promotes them, because the agency has not yet agreed to
 * deliver it.
 */
export type RegistrationStatus = 'active' | 'prospect' | 'stopped';

/** What a notification is about. */
export type NotificationKind =
  'quote-submitted' | 'quote-validated' | 'quote-refused' | 'planning-completed';

/** A signed-in account. */
export interface User {
  id: string | null;
  email: string;
  full_name: string;
  role: UserRole;
  /**
   * The language this holder reads the application in.
   *
   * @remarks
   * Stored on the server, not only in `localStorage`, because it decides
   * what language the quotes emailed to customers are generated in — and
   * those are built by a background webhook with no browser attached.
   */
  language: Language;
  is_active: boolean;
  hca_id: string | null;
  company_id: string | null;
  /**
   * The holder's portrait, when they have uploaded one.
   *
   * On the *account* rather than only on the assistant record, because every
   * signed-in person has an account and only some of them are assistants — a
   * manager had nowhere to put a face at all.
   */
  photo_url: string | null;
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
  /**
   * The catalogue entry this qualification instantiates.
   *
   * @remarks
   * Optional, and the free-text `name` stays beside it, because the catalogue
   * arrived after the records did. Only a coded qualification can be matched
   * against a service's requirement — an untyped name is a record of something
   * somebody holds, not a claim the planner can act on.
   */
  code: string | null;
  issuer: string | null;
  obtained_on: string | null;
  expires_on: string | null;
}

/** A qualification the agency recognises. */
export interface CertificationType {
  id: string | null;
  /**
   * The stable key everything else refers to.
   *
   * @remarks
   * Immutable once created. It is what an assistant's stored qualification and
   * a service's requirement are matched on, so renaming it would disqualify
   * every holder on the next planning run.
   */
  code: string;
  label: string;
  description: string | null;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

/** A partial edit to a certification-catalogue entry. */
export interface CertificationTypeUpdate {
  label?: string;
  description?: string | null;
  is_active?: boolean;
}

/** A skill an assistant declared about themselves. */
export interface Skill {
  /**
   * The identifier a delete addresses.
   *
   * @remarks
   * Present on every stored skill, unlike a {@link Certification}. A skill is
   * removed one at a time — by its owner, a manager or an administrator — so
   * the browser has to be able to name the row it means.
   */
  id: string | null;
  name: string;
  /**
   * The catalogue entry this skill instantiates.
   *
   * @remarks
   * Optional, and the free-text `name` stays beside it: somebody may declare
   * something the catalogue has no name for yet. Only a coded skill can be
   * matched against a service's requirement.
   */
  code: string | null;
  issuer: string | null;
  obtained_on: string | null;
  expires_on: string | null;
}

/**
 * A skill being declared.
 *
 * @remarks
 * Carries no `id` and no assistant. The server takes the owner from the
 * credential and mints the identifier, so this payload cannot file a
 * declaration against a colleague or overwrite an existing one.
 */
export interface SkillCreate {
  name: string;
  code: string | null;
  issuer: string | null;
  obtained_on: string | null;
  expires_on: string | null;
}

/** A skill the agency recognises. */
export interface SkillType {
  id: string | null;
  /**
   * The stable key everything else refers to.
   *
   * @remarks
   * Immutable once created. It is what an assistant's declared skill and a
   * service's requirement are matched on, so renaming it would un-skill every
   * holder on the next planning run.
   */
  code: string;
  label: string;
  description: string | null;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

/** A partial edit to a skill-catalogue entry. */
export interface SkillTypeUpdate {
  label?: string;
  description?: string | null;
  is_active?: boolean;
}

/** An assistant's driving licence. */
export interface DrivingLicense {
  categories: string[];
  number: string | null;
  obtained_on: string | null;
  expires_on: string | null;
}

/**
 * A day of the week. Mirrors `Weekday` on the server.
 *
 * @remarks
 * Ordered Monday first, which is both the ISO order and the order the server
 * sorts a working week into. Rendering from this constant rather than from the
 * order an API response happens to arrive in keeps the checkboxes from moving
 * about between saves.
 */
export const WEEKDAYS = [
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
  'sunday',
] as const;

/** One of the seven days of the week. */
export type Weekday = (typeof WEEKDAYS)[number];

/**
 * The planning rules a manager or administrator owns.
 *
 * @remarks
 * Times are minutes from midnight, not `HH:MM` strings, because that is the
 * unit the solver works in and the API publishes. The forms convert at the
 * edge; see `minutesToTime` and `timeToMinutes` in `@/utils/format`.
 */
export interface PlanningSettings {
  id: string;
  max_intervention_radius_km: number;
  day_start_minute: number;
  day_end_minute: number;
  lunch_break_minutes: number;
  lunch_window_start_minute: number;
  lunch_window_end_minute: number;
  updated_by: string | null;
  updated_at: string | null;
}

/** A language the application, and the documents it emails, speak. */
export type Language = 'fr' | 'en';

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
  /**
   * The skills this assistant declared about themselves.
   *
   * @remarks
   * The one planner-visible field its owner writes. A certification is
   * recorded by a manager; a skill is a claim about what somebody can do, so
   * they enter it themselves and every supervisor is notified.
   */
  skills: Skill[];
  driving_license: DrivingLicense | null;
  photo_url: string | null;
  availability: AvailabilitySlot[];
  /**
   * The days of the week this assistant works at all.
   *
   * @remarks
   * The recurring pattern — "never Wednesdays" — as opposed to `availability`,
   * which records dated absences. The two are separate on purpose: the planner
   * refuses work on both, but only one of them resolves itself when somebody
   * comes back from leave.
   *
   * Never empty. The server refuses a week nobody works rather than reading it
   * as a request for the default.
   */
  working_weekdays: Weekday[];
  /**
   * Whether this person may be placed on an intervention planning.
   *
   * @remarks
   * A property of the person, not of their account's role: a manager who
   * covers rounds and an assistant on office duties are both ordinary, and
   * neither is expressible as a `UserRole`. Defaults to `true`, which is what
   * every record that predates the field already was.
   */
  field_employee: boolean;
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

/**
 * A customer being registered, before the server stores them.
 *
 * @remarks
 * Narrower than `Customer`: no identifier and no timestamps, which the store
 * sets. The address carries no coordinate either — geocoding happens server-side
 * while the payload is validated, and a latitude typed in a browser would be a
 * second answer that can disagree with the one the planner routes to.
 */
export interface NewCustomer {
  first_name: string;
  last_name: string;
  phone_number: string;
  email: string;
  address: {
    street: string;
    postal_code: string;
    city: string;
    country: string;
  };
  registration_status: RegistrationStatus;
}

/**
 * What narrows the customer book.
 *
 * @remarks
 * Mirrors the server's `CustomerFilter`. Every field is optional and an absent
 * one narrows nothing — the screen sends the two boxes somebody filled in, not
 * eight.
 *
 * The flags are three-state on purpose. `undefined` is "do not filter on this";
 * `false` is "only those where it is false", which is a question a manager asks
 * — "whose address failed to resolve?" are exactly the customers nothing can
 * ever be planned for.
 *
 * Filtering runs on the server. The grid holds one page, so a client-side
 * filter would search only the rows it happens to have and silently miss the
 * rest of the book.
 */
export interface CustomerFilter {
  search?: string;
  status?: RegistrationStatus;
  city?: string;
  postal_code?: string;
  email?: string;
  phone?: string;
  has_ongoing_arrangement?: boolean;
  is_geocoded?: boolean;
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
  /**
   * The qualifications this line requires, or `null` to inherit the catalogue.
   *
   * @remarks
   * Three states, and the third is why it is nullable. `null` means "whatever
   * the catalogue entry requires"; an array means "these, instead"; and an
   * **empty** array means "this hour needs no qualification at all", which is
   * a real answer when the catalogue's default is wrong for one customer.
   */
  required_certification_codes: string[] | null;
  /**
   * The skills this line requires, or `null` to inherit the catalogue.
   *
   * @remarks
   * The same three states as `required_certification_codes`, overridden
   * independently — a line that needs the catalogue's diplomas but no
   * particular skill is an ordinary thing to want.
   */
  required_skill_codes: string[] | null;
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
  /**
   * The agency that offers the work.
   *
   * @remarks
   * Read-only from the client's side. It is taken from the credential when a
   * quote is created and decides whose accepted work a planning run schedules,
   * so no payload can set it — see {@link NewQuote} and {@link QuoteLinesEdit},
   * neither of which carries one.
   */
  company_id: string;
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
  /**
   * The last day the arrangement is delivered, or `null` if it runs on.
   *
   * Services dated after it are neither planned nor billed, but they stay on
   * the quote — so the document can still show what the cancelled visits would
   * have cost.
   */
  /**
   * Why the last planning could not fit this quote's work.
   *
   * @remarks
   * `null` is the ordinary case: no note means no problem. When it is set,
   * the quote has been sent back to `pending-validation` — an accepted quote
   * whose work will not fit is not a settled commitment — and this says which
   * visits failed, why, and when somebody qualified is free instead.
   */
  planning_feedback: UnplacedQuote | null;
  interrupted_on: string | null;
  /** Whether a successor is written when this quote expires. */
  auto_renew: boolean;
  /** The quote this one succeeds, when a renewal created it. */
  renewed_from_id: string | null;
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
  /**
   * The qualifications an assistant must hold to be given this work.
   *
   * @remarks
   * Empty by default, so nothing already being sold suddenly requires a
   * diploma nobody holds. A quote line may override it.
   */
  required_certification_codes: string[];
  /**
   * The skills an assistant must have declared to be given this work.
   *
   * @remarks
   * A second, independent list rather than more entries in the first. The
   * planner reports the two as different reasons for leaving work unplaced:
   * "nobody holds DEAES" is a hire, "nobody has declared LEVE-PERSONNE" may be
   * somebody who can already do it not having said so.
   */
  required_skill_codes: string[];
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
/** Why one visit could not be placed. Mirrors `UnplacedReason` on the server. */
export type UnplacedReason =
  | 'out-of-radius'
  | 'not-a-working-day'
  | 'no-assistant-available'
  | 'outside-working-day'
  | 'missing-certification'
  | 'missing-skill'
  | 'customer-conflict'
  | 'no-feasible-slot';

/** The body of a quote header edit. */
export interface QuoteHeaderEdit {
  reference: string;
  customer_id: string;
  issued_on: string | null;
  valid_until: string | null;
  auto_renew: boolean;
}

/** A time somebody qualified is free, offered in place of one that failed. */
export interface SuggestedSlot {
  day: string;
  start_minute: number;
  end_minute: number;
  hca_id: string;
  hca_name: string;
}

/** One visit a run could not fit, and why. */
export interface UnplacedVisit {
  requirement_id: string;
  name: string;
  customer_id: string;
  customer_name: string;
  quote_reference: string;
  day: string;
  reason: UnplacedReason;
  detail: string | null;
  /**
   * The quote line this work was sold on.
   *
   * @remarks
   * What makes an offered slot actionable: accepting one moves *this* line.
   * Null on a note written before the field existed, in which case the slots
   * are shown but not offered as clickable — there is nothing to move.
   */
  quote_line_id: string | null;
  /**
   * Times somebody qualified is free instead of this visit's.
   *
   * @remarks
   * Per visit, not per quote. A quote with two unplaced visits has two sets of
   * free times, and one flat list leaves an operator guessing which slot
   * answers which problem.
   */
  alternatives: SuggestedSlot[];
}

/**
 * Everything one quote could not fit into a week.
 *
 * @remarks
 * Grouped by quote because that is the unit somebody can act on: a list of
 * thirty visits says something is wrong, where "quote DEV-2026-0042 for Marie
 * Durand, three visits, nobody holds DEAES" says who to telephone.
 */
export interface UnplacedQuote {
  quote_reference: string;
  customer_id: string;
  customer_name: string;
  visits: UnplacedVisit[];
  /**
   * Times somebody qualified is free, offered instead.
   *
   * @remarks
   * Offers, not bookings. Nothing is reserved: two operators acting on the
   * same suggestion are both told it fits, and the next planning run settles
   * it. Empty means the week is full for everybody qualified, which is itself
   * an answer.
   */
  alternatives: SuggestedSlot[];
}

/** The slot an operator accepted, for one line of a returned quote. */
export interface QuoteReschedule {
  quote_line_id: string;
  day: string;
  start_minute: number;
  end_minute: number;
}

export interface PlanningRun {
  id: string | null;
  status: 'pending' | 'running' | 'succeeded' | 'partial' | 'failed';
  requested_by: string;
  period_start: string;
  period_end: string;
  started_at: string | null;
  finished_at: string | null;
  total_travel_minutes: number | null;
  scheduled_count: number | null;
  /**
   * Whether the driving in the stored plan was proved as short as it can be.
   *
   * @remarks
   * A run places every visit first and shortens the rounds second. If the
   * second pass runs out of budget the first pass's plan is stored unchanged
   * — nothing is left unscheduled, the travel simply was not proved minimal.
   *
   * `null` is not `false`: a run from before the two-pass solve never asked
   * the question, and rendering it as unoptimised would invent a finding
   * about a historic plan.
   */
  is_optimised: boolean | null;
  /**
   * One entry per quote whose work could not all be fitted.
   *
   * @remarks
   * Empty on a run that placed everything. The screen renders this rather
   * than `error_message` for a partial run: the message is one long sentence
   * built server-side, and it can neither be translated nor grouped.
   */
  unplaced_quotes: UnplacedQuote[];
  unassigned_requirement_ids: string[];
  error_message: string | null;
}

/** An agency. */
export interface Company {
  /** Identifier. */
  id: string;
  /** Trading name. */
  name: string;
  /**
   * Registration number, when the agency has been issued one.
   *
   * @remarks
   * This and the five fields below are what a quote must say about whoever
   * is making the offer. All are nullable: none has a safe default, and an
   * agency prints only what it has filled in.
   */
  registration_number: string | null;
  /** Legal form, such as SARL, SAS or Association. */
  legal_form: string | null;
  /** Share capital in euros, as a decimal string. */
  share_capital: string | null;
  /** Trade-register entry, such as "RCS Paris B 123 456 789". */
  rcs_number: string | null;
  /** Intra-community VAT number, such as FR12345678901. */
  vat_number: string | null;
  /** Contact telephone number. */
  phone_number: string | null;
  /** Contact address. */
  contact_email: string | null;
  /** Registered address, when one has been recorded. */
  address: PostalAddress | null;
  /**
   * The account the agency is paid into, for SEPA transfers.
   *
   * @remarks
   * Only `GET /me/company` — administrator-gated — returns this whole. The
   * agency routes a manager can reach hand back a masked form instead, so a
   * value read from anywhere else must never be sent back on a save.
   */
  iban: string | null;
  /** Bank identifier code of that account. */
  bic: string | null;
  /**
   * URL of the agency's logo in the object store.
   *
   * @remarks
   * Read-only here. It is written by `PUT /me/company/logo`, which uploads
   * the image and then records where it put it — the profile payload cannot
   * carry it.
   */
  logo_url: string | null;
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
 * Deliberately narrower than `Company`: no identifier, no timestamps, and no
 * `logo_url`. The server's payload model carries the same fields and no
 * others, so the two agree by construction rather than by anybody remembering
 * to keep them so.
 */
export interface CompanyProfileUpdate {
  name: string;
  registration_number: string | null;
  legal_form: string | null;
  share_capital: string | null;
  rcs_number: string | null;
  vat_number: string | null;
  phone_number: string | null;
  iban: string | null;
  bic: string | null;
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
  /**
   * The qualifications this service requires.
   *
   * @remarks
   * Omitted means "leave them alone"; an empty array means "require nothing
   * from now on". The two are different requests, which is why every field
   * here is optional and the caller sends only what it changed.
   */
  required_certification_codes?: string[];
  /**
   * The skills this service requires.
   *
   * @remarks
   * Omitted means "leave them alone"; an empty array means "require nothing
   * from now on", exactly as for the qualifications above.
   */
  required_skill_codes?: string[];
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
  /**
   * The qualifications it requires, or `null` to inherit the catalogue entry.
   *
   * @remarks
   * The dialogs pre-fill this from the chosen service and leave it editable,
   * exactly as they do the VAT category — only the person writing the quote
   * knows whether this customer's hours are the ordinary case.
   */
  required_certification_codes: string[] | null;
  /**
   * The skills it requires, or `null` to inherit the catalogue entry.
   *
   * @remarks
   * Pre-filled from the chosen service and left editable, like the
   * qualifications above it.
   */
  required_skill_codes: string[] | null;
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

/**
 * The body of `PUT /quotes/{id}/lines`.
 *
 * @remarks
 * Only the lines, and that is the whole point. The endpoint used to accept a
 * whole {@link Quote} and read one field of it, so a client could send a
 * reference, a customer or a status and watch them be quietly ignored — and,
 * once a quote carried its agency, could have moved one between agencies. The
 * server now takes this shape, so there is nothing else to send.
 */
export interface QuoteLinesEdit {
  /** The services that replace the stored ones. */
  lines: NewQuoteLine[];
}
