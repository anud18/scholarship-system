--
-- PostgreSQL database dump
--

-- Dumped from database version 15.13
-- Dumped by pg_dump version 15.13

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: applicationcycle; Type: TYPE; Schema: public; Owner: scholarship_user
--

CREATE TYPE public.applicationcycle AS ENUM (
    'semester',
    'yearly'
);


ALTER TYPE public.applicationcycle OWNER TO scholarship_user;

--
-- Name: applicationstatus; Type: TYPE; Schema: public; Owner: scholarship_user
--

CREATE TYPE public.applicationstatus AS ENUM (
    'draft',
    'submitted',
    'under_review',
    'approved',
    'rejected',
    'withdrawn'
);


ALTER TYPE public.applicationstatus OWNER TO scholarship_user;

--
-- Name: configcategory; Type: TYPE; Schema: public; Owner: scholarship_user
--

CREATE TYPE public.configcategory AS ENUM (
    'database',
    'api_keys',
    'email',
    'ocr',
    'file_storage',
    'security',
    'features',
    'integrations',
    'performance',
    'logging'
);


ALTER TYPE public.configcategory OWNER TO scholarship_user;

--
-- Name: configdatatype; Type: TYPE; Schema: public; Owner: scholarship_user
--

CREATE TYPE public.configdatatype AS ENUM (
    'string',
    'integer',
    'boolean',
    'json',
    'float'
);


ALTER TYPE public.configdatatype OWNER TO scholarship_user;

--
-- Name: emailcategory; Type: TYPE; Schema: public; Owner: scholarship_user
--

CREATE TYPE public.emailcategory AS ENUM (
    'application_confirmation',
    'review_request',
    'decision_notification',
    'reminder',
    'system_notification',
    'custom'
);


ALTER TYPE public.emailcategory OWNER TO scholarship_user;

--
-- Name: emailstatus; Type: TYPE; Schema: public; Owner: scholarship_user
--

CREATE TYPE public.emailstatus AS ENUM (
    'pending',
    'sent',
    'failed',
    'cancelled'
);


ALTER TYPE public.emailstatus OWNER TO scholarship_user;

--
-- Name: employeestatus; Type: TYPE; Schema: public; Owner: scholarship_user
--

CREATE TYPE public.employeestatus AS ENUM (
    '在職',
    '退休',
    '在學',
    '畢業'
);


ALTER TYPE public.employeestatus OWNER TO scholarship_user;

--
-- Name: notificationchannel; Type: TYPE; Schema: public; Owner: scholarship_user
--

CREATE TYPE public.notificationchannel AS ENUM (
    'in_app',
    'email',
    'sms',
    'push'
);


ALTER TYPE public.notificationchannel OWNER TO scholarship_user;

--
-- Name: notificationfrequency; Type: TYPE; Schema: public; Owner: scholarship_user
--

CREATE TYPE public.notificationfrequency AS ENUM (
    'IMMEDIATE',
    'DAILY',
    'WEEKLY',
    'DISABLED'
);


ALTER TYPE public.notificationfrequency OWNER TO scholarship_user;

--
-- Name: notificationpriority; Type: TYPE; Schema: public; Owner: scholarship_user
--

CREATE TYPE public.notificationpriority AS ENUM (
    'LOW',
    'NORMAL',
    'HIGH',
    'URGENT'
);


ALTER TYPE public.notificationpriority OWNER TO scholarship_user;

--
-- Name: notificationtype; Type: TYPE; Schema: public; Owner: scholarship_user
--

CREATE TYPE public.notificationtype AS ENUM (
    'INFO',
    'WARNING',
    'ERROR',
    'SUCCESS',
    'REMINDER'
);


ALTER TYPE public.notificationtype OWNER TO scholarship_user;

--
-- Name: quotamanagementmode; Type: TYPE; Schema: public; Owner: scholarship_user
--

CREATE TYPE public.quotamanagementmode AS ENUM (
    'none',
    'simple',
    'college_based',
    'matrix_based'
);


ALTER TYPE public.quotamanagementmode OWNER TO scholarship_user;

--
-- Name: semester; Type: TYPE; Schema: public; Owner: scholarship_user
--

CREATE TYPE public.semester AS ENUM (
    'FIRST',
    'SECOND',
    'SUMMER',
    'ANNUAL'
);


ALTER TYPE public.semester OWNER TO scholarship_user;

--
-- Name: sendingtype; Type: TYPE; Schema: public; Owner: scholarship_user
--

CREATE TYPE public.sendingtype AS ENUM (
    'single',
    'bulk'
);


ALTER TYPE public.sendingtype OWNER TO scholarship_user;

--
-- Name: subtypeselectionmode; Type: TYPE; Schema: public; Owner: scholarship_user
--

CREATE TYPE public.subtypeselectionmode AS ENUM (
    'single',
    'multiple',
    'hierarchical'
);


ALTER TYPE public.subtypeselectionmode OWNER TO scholarship_user;

--
-- Name: userrole; Type: TYPE; Schema: public; Owner: scholarship_user
--

CREATE TYPE public.userrole AS ENUM (
    'student',
    'professor',
    'college',
    'admin',
    'super_admin'
);


ALTER TYPE public.userrole OWNER TO scholarship_user;

--
-- Name: usertype; Type: TYPE; Schema: public; Owner: scholarship_user
--

CREATE TYPE public.usertype AS ENUM (
    'student',
    'employee'
);


ALTER TYPE public.usertype OWNER TO scholarship_user;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: academies; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.academies (
    id integer NOT NULL,
    code character varying(10) NOT NULL,
    name character varying(100) NOT NULL
);


ALTER TABLE public.academies OWNER TO scholarship_user;

--
-- Name: academies_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.academies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.academies_id_seq OWNER TO scholarship_user;

--
-- Name: academies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.academies_id_seq OWNED BY public.academies.id;


--
-- Name: admin_scholarships; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.admin_scholarships (
    id integer NOT NULL,
    admin_id integer NOT NULL,
    scholarship_id integer NOT NULL,
    assigned_at timestamp without time zone
);


ALTER TABLE public.admin_scholarships OWNER TO scholarship_user;

--
-- Name: admin_scholarships_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.admin_scholarships_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.admin_scholarships_id_seq OWNER TO scholarship_user;

--
-- Name: admin_scholarships_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.admin_scholarships_id_seq OWNED BY public.admin_scholarships.id;


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO scholarship_user;

--
-- Name: application_documents; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.application_documents (
    id integer NOT NULL,
    scholarship_type character varying(50) NOT NULL,
    document_name character varying(200) NOT NULL,
    document_name_en character varying(200),
    description text,
    description_en text,
    is_required boolean,
    accepted_file_types json,
    max_file_size character varying(20),
    max_file_count integer,
    display_order integer,
    is_active boolean,
    upload_instructions text,
    upload_instructions_en text,
    validation_rules json,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    created_by integer,
    updated_by integer
);


ALTER TABLE public.application_documents OWNER TO scholarship_user;

--
-- Name: application_documents_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.application_documents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.application_documents_id_seq OWNER TO scholarship_user;

--
-- Name: application_documents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.application_documents_id_seq OWNED BY public.application_documents.id;


--
-- Name: application_fields; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.application_fields (
    id integer NOT NULL,
    scholarship_type character varying(50) NOT NULL,
    field_name character varying(100) NOT NULL,
    field_label character varying(200) NOT NULL,
    field_label_en character varying(200),
    field_type character varying(20) NOT NULL,
    is_required boolean,
    placeholder character varying(500),
    placeholder_en character varying(500),
    max_length integer,
    min_value double precision,
    max_value double precision,
    step_value double precision,
    field_options json,
    display_order integer,
    is_active boolean,
    help_text text,
    help_text_en text,
    validation_rules json,
    conditional_rules json,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    created_by integer,
    updated_by integer
);


ALTER TABLE public.application_fields OWNER TO scholarship_user;

--
-- Name: application_fields_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.application_fields_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.application_fields_id_seq OWNER TO scholarship_user;

--
-- Name: application_fields_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.application_fields_id_seq OWNED BY public.application_fields.id;


--
-- Name: application_files; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.application_files (
    id integer NOT NULL,
    application_id integer NOT NULL,
    filename character varying(255) NOT NULL,
    original_filename character varying(255),
    object_name character varying(500),
    file_size integer,
    mime_type character varying(100),
    content_type character varying(100),
    file_type character varying(50),
    ocr_processed boolean,
    ocr_text text,
    ocr_confidence numeric(5,2),
    is_verified boolean,
    verification_notes text,
    uploaded_at timestamp with time zone DEFAULT now(),
    upload_date timestamp with time zone DEFAULT now(),
    processed_at timestamp with time zone
);


ALTER TABLE public.application_files OWNER TO scholarship_user;

--
-- Name: application_files_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.application_files_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.application_files_id_seq OWNER TO scholarship_user;

--
-- Name: application_files_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.application_files_id_seq OWNED BY public.application_files.id;


--
-- Name: application_reviews; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.application_reviews (
    id integer NOT NULL,
    application_id integer NOT NULL,
    reviewer_id integer NOT NULL,
    review_stage character varying(50),
    review_status character varying(20),
    score numeric(5,2),
    comments text,
    recommendation text,
    decision_reason text,
    criteria_scores json,
    assigned_at timestamp with time zone DEFAULT now(),
    reviewed_at timestamp with time zone,
    due_date timestamp with time zone
);


ALTER TABLE public.application_reviews OWNER TO scholarship_user;

--
-- Name: application_reviews_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.application_reviews_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.application_reviews_id_seq OWNER TO scholarship_user;

--
-- Name: application_reviews_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.application_reviews_id_seq OWNED BY public.application_reviews.id;


--
-- Name: applications; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.applications (
    id integer NOT NULL,
    app_id character varying(20) NOT NULL,
    user_id integer NOT NULL,
    scholarship_type_id integer,
    scholarship_configuration_id integer,
    scholarship_name character varying(200),
    amount numeric(10,2),
    scholarship_subtype_list json NOT NULL,
    sub_type_selection_mode public.subtypeselectionmode NOT NULL,
    main_scholarship_type character varying(50),
    sub_scholarship_type character varying(50),
    is_renewal boolean NOT NULL,
    previous_application_id integer,
    priority_score integer,
    review_deadline timestamp with time zone,
    decision_date timestamp with time zone,
    status character varying(50),
    status_name character varying(100),
    academic_year integer NOT NULL,
    semester public.semester,
    student_data json,
    submitted_form_data json,
    agree_terms boolean,
    professor_id integer,
    reviewer_id integer,
    final_approver_id integer,
    review_score numeric(5,2),
    review_comments text,
    rejection_reason text,
    college_ranking_score numeric(8,2),
    final_ranking_position integer,
    quota_allocation_status character varying(20),
    submitted_at timestamp with time zone,
    reviewed_at timestamp with time zone,
    approved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    meta_data json
);


ALTER TABLE public.applications OWNER TO scholarship_user;

--
-- Name: applications_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.applications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.applications_id_seq OWNER TO scholarship_user;

--
-- Name: applications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.applications_id_seq OWNED BY public.applications.id;


--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.audit_logs (
    id integer NOT NULL,
    user_id integer NOT NULL,
    action character varying(50) NOT NULL,
    resource_type character varying(50) NOT NULL,
    resource_id character varying(50),
    resource_name character varying(200),
    description text,
    old_values json,
    new_values json,
    ip_address character varying(45),
    user_agent text,
    request_method character varying(10),
    request_url character varying(500),
    request_headers json,
    status character varying(20),
    error_message text,
    response_time_ms integer,
    created_at timestamp with time zone DEFAULT now(),
    trace_id character varying(100),
    session_id character varying(100),
    meta_data json
);


ALTER TABLE public.audit_logs OWNER TO scholarship_user;

--
-- Name: audit_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.audit_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.audit_logs_id_seq OWNER TO scholarship_user;

--
-- Name: audit_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.audit_logs_id_seq OWNED BY public.audit_logs.id;


--
-- Name: college_ranking_items; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.college_ranking_items (
    id integer NOT NULL,
    ranking_id integer NOT NULL,
    application_id integer NOT NULL,
    college_review_id integer NOT NULL,
    rank_position integer NOT NULL,
    is_allocated boolean,
    allocation_reason text,
    total_score numeric(8,2),
    tie_breaker_applied boolean,
    tie_breaker_reason text,
    status character varying(20),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.college_ranking_items OWNER TO scholarship_user;

--
-- Name: college_ranking_items_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.college_ranking_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.college_ranking_items_id_seq OWNER TO scholarship_user;

--
-- Name: college_ranking_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.college_ranking_items_id_seq OWNED BY public.college_ranking_items.id;


--
-- Name: college_rankings; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.college_rankings (
    id integer NOT NULL,
    scholarship_type_id integer NOT NULL,
    sub_type_code character varying(50) NOT NULL,
    academic_year integer NOT NULL,
    semester character varying(20),
    ranking_name character varying(200),
    total_applications integer,
    total_quota integer,
    allocated_count integer,
    is_finalized boolean,
    ranking_status character varying(20),
    distribution_executed boolean,
    distribution_date timestamp with time zone,
    github_issue_url character varying(500),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    finalized_at timestamp with time zone,
    created_by integer,
    finalized_by integer
);


ALTER TABLE public.college_rankings OWNER TO scholarship_user;

--
-- Name: college_rankings_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.college_rankings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.college_rankings_id_seq OWNER TO scholarship_user;

--
-- Name: college_rankings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.college_rankings_id_seq OWNED BY public.college_rankings.id;


--
-- Name: college_reviews; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.college_reviews (
    id integer NOT NULL,
    application_id integer NOT NULL,
    reviewer_id integer NOT NULL,
    ranking_score numeric(8,2),
    academic_score numeric(5,2),
    professor_review_score numeric(5,2),
    college_criteria_score numeric(5,2),
    special_circumstances_score numeric(5,2),
    review_comments text,
    recommendation character varying(20),
    decision_reason text,
    preliminary_rank integer,
    final_rank integer,
    sub_type_group character varying(50),
    review_status character varying(20),
    is_priority boolean,
    needs_special_attention boolean,
    scoring_weights jsonb,
    review_started_at timestamp with time zone,
    reviewed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT check_academic_score_range CHECK (((academic_score IS NULL) OR ((academic_score >= (0)::numeric) AND (academic_score <= (100)::numeric)))),
    CONSTRAINT check_college_score_range CHECK (((college_criteria_score IS NULL) OR ((college_criteria_score >= (0)::numeric) AND (college_criteria_score <= (100)::numeric)))),
    CONSTRAINT check_professor_score_range CHECK (((professor_review_score IS NULL) OR ((professor_review_score >= (0)::numeric) AND (professor_review_score <= (100)::numeric)))),
    CONSTRAINT check_ranking_score_range CHECK (((ranking_score IS NULL) OR ((ranking_score >= (0)::numeric) AND (ranking_score <= (100)::numeric)))),
    CONSTRAINT check_special_score_range CHECK (((special_circumstances_score IS NULL) OR ((special_circumstances_score >= (0)::numeric) AND (special_circumstances_score <= (100)::numeric))))
);


ALTER TABLE public.college_reviews OWNER TO scholarship_user;

--
-- Name: college_reviews_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.college_reviews_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.college_reviews_id_seq OWNER TO scholarship_user;

--
-- Name: college_reviews_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.college_reviews_id_seq OWNED BY public.college_reviews.id;


--
-- Name: configuration_audit_logs; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.configuration_audit_logs (
    id integer NOT NULL,
    setting_key character varying(100) NOT NULL,
    old_value text,
    new_value text NOT NULL,
    action character varying(20) NOT NULL,
    changed_by integer NOT NULL,
    change_reason text,
    changed_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.configuration_audit_logs OWNER TO scholarship_user;

--
-- Name: configuration_audit_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.configuration_audit_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.configuration_audit_logs_id_seq OWNER TO scholarship_user;

--
-- Name: configuration_audit_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.configuration_audit_logs_id_seq OWNED BY public.configuration_audit_logs.id;


--
-- Name: degrees; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.degrees (
    id smallint NOT NULL,
    name character varying(20) NOT NULL
);


ALTER TABLE public.degrees OWNER TO scholarship_user;

--
-- Name: degrees_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.degrees_id_seq
    AS smallint
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.degrees_id_seq OWNER TO scholarship_user;

--
-- Name: degrees_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.degrees_id_seq OWNED BY public.degrees.id;


--
-- Name: departments; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.departments (
    id integer NOT NULL,
    code character varying(10),
    name character varying(100) NOT NULL
);


ALTER TABLE public.departments OWNER TO scholarship_user;

--
-- Name: departments_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.departments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.departments_id_seq OWNER TO scholarship_user;

--
-- Name: departments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.departments_id_seq OWNED BY public.departments.id;


--
-- Name: email_templates; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.email_templates (
    id integer NOT NULL,
    key character varying(100) NOT NULL,
    subject_template character varying(255) NOT NULL,
    body_template text NOT NULL,
    cc text,
    bcc text,
    sending_type public.sendingtype NOT NULL,
    recipient_options json,
    requires_approval boolean NOT NULL,
    max_recipients integer,
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.email_templates OWNER TO scholarship_user;

--
-- Name: email_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.email_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.email_templates_id_seq OWNER TO scholarship_user;

--
-- Name: email_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.email_templates_id_seq OWNED BY public.email_templates.id;


--
-- Name: enroll_types; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.enroll_types (
    "degreeId" smallint NOT NULL,
    code smallint NOT NULL,
    name character varying(100) NOT NULL,
    name_en character varying(100) NOT NULL
);


ALTER TABLE public.enroll_types OWNER TO scholarship_user;

--
-- Name: identities; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.identities (
    id smallint NOT NULL,
    name character varying(100) NOT NULL
);


ALTER TABLE public.identities OWNER TO scholarship_user;

--
-- Name: identities_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.identities_id_seq
    AS smallint
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.identities_id_seq OWNER TO scholarship_user;

--
-- Name: identities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.identities_id_seq OWNED BY public.identities.id;


--
-- Name: notification_preferences; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.notification_preferences (
    id integer NOT NULL,
    user_id integer NOT NULL,
    notification_type public.notificationtype NOT NULL,
    in_app_enabled boolean NOT NULL,
    email_enabled boolean NOT NULL,
    sms_enabled boolean NOT NULL,
    push_enabled boolean NOT NULL,
    frequency public.notificationfrequency NOT NULL,
    quiet_hours_start character varying(5),
    quiet_hours_end character varying(5),
    timezone character varying(50) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.notification_preferences OWNER TO scholarship_user;

--
-- Name: notification_preferences_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.notification_preferences_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.notification_preferences_id_seq OWNER TO scholarship_user;

--
-- Name: notification_preferences_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.notification_preferences_id_seq OWNED BY public.notification_preferences.id;


--
-- Name: notification_queue; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.notification_queue (
    id integer NOT NULL,
    user_id integer NOT NULL,
    batch_id character varying(50) NOT NULL,
    notification_type public.notificationtype NOT NULL,
    priority public.notificationpriority,
    notifications_data json NOT NULL,
    aggregated_content json,
    scheduled_for timestamp with time zone NOT NULL,
    attempts integer,
    max_attempts integer,
    status character varying(20),
    error_message text,
    created_at timestamp with time zone DEFAULT now(),
    processed_at timestamp with time zone
);


ALTER TABLE public.notification_queue OWNER TO scholarship_user;

--
-- Name: notification_queue_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.notification_queue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.notification_queue_id_seq OWNER TO scholarship_user;

--
-- Name: notification_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.notification_queue_id_seq OWNED BY public.notification_queue.id;


--
-- Name: notification_reads; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.notification_reads (
    id integer NOT NULL,
    notification_id integer NOT NULL,
    user_id integer NOT NULL,
    is_read boolean,
    read_at timestamp with time zone DEFAULT now(),
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.notification_reads OWNER TO scholarship_user;

--
-- Name: notification_reads_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.notification_reads_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.notification_reads_id_seq OWNER TO scholarship_user;

--
-- Name: notification_reads_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.notification_reads_id_seq OWNED BY public.notification_reads.id;


--
-- Name: notification_templates; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.notification_templates (
    id integer NOT NULL,
    type public.notificationtype NOT NULL,
    title_template character varying(255) NOT NULL,
    title_template_en character varying(255),
    message_template text NOT NULL,
    message_template_en text,
    href_template character varying(500),
    default_channels json,
    default_priority public.notificationpriority,
    variables json,
    is_active boolean NOT NULL,
    requires_user_action boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.notification_templates OWNER TO scholarship_user;

--
-- Name: notification_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.notification_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.notification_templates_id_seq OWNER TO scholarship_user;

--
-- Name: notification_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.notification_templates_id_seq OWNED BY public.notification_templates.id;


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.notifications (
    id integer NOT NULL,
    user_id integer,
    title character varying(255) NOT NULL,
    title_en character varying(255),
    message text NOT NULL,
    message_en text,
    notification_type public.notificationtype NOT NULL,
    priority public.notificationpriority NOT NULL,
    channel public.notificationchannel NOT NULL,
    data json,
    href character varying(500),
    related_resource_type character varying(50),
    related_resource_id integer,
    action_url character varying(500),
    meta_data json,
    is_read boolean NOT NULL,
    is_dismissed boolean NOT NULL,
    is_archived boolean NOT NULL,
    is_hidden boolean NOT NULL,
    send_email boolean,
    email_sent boolean,
    email_sent_at timestamp with time zone,
    group_key character varying(100),
    batch_id character varying(50),
    scheduled_at timestamp with time zone,
    scheduled_for timestamp with time zone,
    expires_at timestamp with time zone,
    read_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.notifications OWNER TO scholarship_user;

--
-- Name: notifications_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.notifications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.notifications_id_seq OWNER TO scholarship_user;

--
-- Name: notifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.notifications_id_seq OWNED BY public.notifications.id;


--
-- Name: professor_review_items; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.professor_review_items (
    id integer NOT NULL,
    review_id integer NOT NULL,
    sub_type_code character varying(50) NOT NULL,
    is_recommended boolean NOT NULL,
    comments text,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.professor_review_items OWNER TO scholarship_user;

--
-- Name: professor_review_items_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.professor_review_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.professor_review_items_id_seq OWNER TO scholarship_user;

--
-- Name: professor_review_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.professor_review_items_id_seq OWNED BY public.professor_review_items.id;


--
-- Name: professor_reviews; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.professor_reviews (
    id integer NOT NULL,
    application_id integer NOT NULL,
    professor_id integer NOT NULL,
    recommendation text,
    review_status character varying(20),
    reviewed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.professor_reviews OWNER TO scholarship_user;

--
-- Name: professor_reviews_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.professor_reviews_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.professor_reviews_id_seq OWNER TO scholarship_user;

--
-- Name: professor_reviews_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.professor_reviews_id_seq OWNED BY public.professor_reviews.id;


--
-- Name: professor_student_relationships; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.professor_student_relationships (
    id integer NOT NULL,
    professor_id integer NOT NULL,
    student_id integer NOT NULL,
    relationship_type character varying(50) NOT NULL,
    department character varying(100),
    academic_year integer,
    semester character varying(20),
    is_active boolean NOT NULL,
    can_view_applications boolean NOT NULL,
    can_upload_documents boolean NOT NULL,
    can_review_applications boolean NOT NULL,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    created_by integer,
    notes character varying(500)
);


ALTER TABLE public.professor_student_relationships OWNER TO scholarship_user;

--
-- Name: professor_student_relationships_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.professor_student_relationships_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.professor_student_relationships_id_seq OWNER TO scholarship_user;

--
-- Name: professor_student_relationships_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.professor_student_relationships_id_seq OWNED BY public.professor_student_relationships.id;


--
-- Name: quota_distributions; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.quota_distributions (
    id integer NOT NULL,
    distribution_name character varying(200) NOT NULL,
    academic_year integer NOT NULL,
    semester character varying(20),
    total_applications integer,
    total_quota integer,
    total_allocated integer,
    algorithm_version character varying(50),
    scoring_weights jsonb,
    distribution_rules jsonb,
    distribution_summary jsonb,
    exceptions jsonb,
    github_issue_number integer,
    github_issue_url character varying(500),
    executed_at timestamp with time zone DEFAULT now(),
    executed_by integer
);


ALTER TABLE public.quota_distributions OWNER TO scholarship_user;

--
-- Name: quota_distributions_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.quota_distributions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.quota_distributions_id_seq OWNER TO scholarship_user;

--
-- Name: quota_distributions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.quota_distributions_id_seq OWNED BY public.quota_distributions.id;


--
-- Name: scholarship_configurations; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.scholarship_configurations (
    id integer NOT NULL,
    scholarship_type_id integer NOT NULL,
    academic_year integer NOT NULL,
    semester public.semester,
    config_name character varying(200) NOT NULL,
    config_code character varying(50) NOT NULL,
    description text,
    description_en text,
    has_quota_limit boolean NOT NULL,
    has_college_quota boolean NOT NULL,
    quota_management_mode public.quotamanagementmode NOT NULL,
    total_quota integer,
    quotas json,
    amount integer NOT NULL,
    currency character varying(10),
    whitelist_student_ids json,
    renewal_application_start_date timestamp with time zone,
    renewal_application_end_date timestamp with time zone,
    application_start_date timestamp with time zone,
    application_end_date timestamp with time zone,
    renewal_professor_review_start timestamp with time zone,
    renewal_professor_review_end timestamp with time zone,
    renewal_college_review_start timestamp with time zone,
    renewal_college_review_end timestamp with time zone,
    requires_professor_recommendation boolean,
    professor_review_start timestamp with time zone,
    professor_review_end timestamp with time zone,
    requires_college_review boolean,
    college_review_start timestamp with time zone,
    college_review_end timestamp with time zone,
    review_deadline timestamp with time zone,
    is_active boolean NOT NULL,
    effective_start_date timestamp with time zone,
    effective_end_date timestamp with time zone,
    version character varying(20),
    previous_config_id integer,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    created_by integer,
    updated_by integer
);


ALTER TABLE public.scholarship_configurations OWNER TO scholarship_user;

--
-- Name: scholarship_configurations_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.scholarship_configurations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.scholarship_configurations_id_seq OWNER TO scholarship_user;

--
-- Name: scholarship_configurations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.scholarship_configurations_id_seq OWNED BY public.scholarship_configurations.id;


--
-- Name: scholarship_rules; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.scholarship_rules (
    id integer NOT NULL,
    scholarship_type_id integer NOT NULL,
    sub_type character varying(50),
    academic_year integer,
    semester public.semester,
    is_template boolean NOT NULL,
    template_name character varying(100),
    template_description text,
    rule_name character varying(100) NOT NULL,
    rule_type character varying(50) NOT NULL,
    tag character varying(20),
    description text,
    condition_field character varying(100),
    operator character varying(20),
    expected_value character varying(500),
    message text,
    message_en text,
    is_hard_rule boolean,
    is_warning boolean,
    priority integer,
    is_active boolean,
    is_initial_enabled boolean NOT NULL,
    is_renewal_enabled boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    created_by integer,
    updated_by integer
);


ALTER TABLE public.scholarship_rules OWNER TO scholarship_user;

--
-- Name: scholarship_rules_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.scholarship_rules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.scholarship_rules_id_seq OWNER TO scholarship_user;

--
-- Name: scholarship_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.scholarship_rules_id_seq OWNED BY public.scholarship_rules.id;


--
-- Name: scholarship_sub_type_configs; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.scholarship_sub_type_configs (
    id integer NOT NULL,
    scholarship_type_id integer NOT NULL,
    sub_type_code character varying(50) NOT NULL,
    name character varying(200) NOT NULL,
    name_en character varying(200),
    description text,
    description_en text,
    amount numeric(10,2),
    currency character varying(10),
    display_order integer,
    is_active boolean,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    created_by integer,
    updated_by integer
);


ALTER TABLE public.scholarship_sub_type_configs OWNER TO scholarship_user;

--
-- Name: scholarship_sub_type_configs_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.scholarship_sub_type_configs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.scholarship_sub_type_configs_id_seq OWNER TO scholarship_user;

--
-- Name: scholarship_sub_type_configs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.scholarship_sub_type_configs_id_seq OWNED BY public.scholarship_sub_type_configs.id;


--
-- Name: scholarship_types; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.scholarship_types (
    id integer NOT NULL,
    code character varying(50) NOT NULL,
    name character varying(200) NOT NULL,
    name_en character varying(200),
    description text,
    description_en text,
    category character varying(50) NOT NULL,
    sub_type_list json,
    sub_type_selection_mode public.subtypeselectionmode NOT NULL,
    application_cycle public.applicationcycle NOT NULL,
    whitelist_enabled boolean,
    status character varying(20),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    created_by integer,
    updated_by integer
);


ALTER TABLE public.scholarship_types OWNER TO scholarship_user;

--
-- Name: scholarship_types_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.scholarship_types_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.scholarship_types_id_seq OWNER TO scholarship_user;

--
-- Name: scholarship_types_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.scholarship_types_id_seq OWNED BY public.scholarship_types.id;


--
-- Name: school_identities; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.school_identities (
    id smallint NOT NULL,
    name character varying(50)
);


ALTER TABLE public.school_identities OWNER TO scholarship_user;

--
-- Name: school_identities_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.school_identities_id_seq
    AS smallint
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.school_identities_id_seq OWNER TO scholarship_user;

--
-- Name: school_identities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.school_identities_id_seq OWNED BY public.school_identities.id;


--
-- Name: studying_statuses; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.studying_statuses (
    id smallint NOT NULL,
    name character varying(50)
);


ALTER TABLE public.studying_statuses OWNER TO scholarship_user;

--
-- Name: studying_statuses_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.studying_statuses_id_seq
    AS smallint
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.studying_statuses_id_seq OWNER TO scholarship_user;

--
-- Name: studying_statuses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.studying_statuses_id_seq OWNED BY public.studying_statuses.id;


--
-- Name: system_settings; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.system_settings (
    id integer NOT NULL,
    key character varying(100) NOT NULL,
    value text NOT NULL,
    category public.configcategory NOT NULL,
    data_type public.configdatatype NOT NULL,
    is_sensitive boolean NOT NULL,
    is_readonly boolean NOT NULL,
    description text,
    validation_regex character varying(255),
    default_value text,
    last_modified_by integer,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.system_settings OWNER TO scholarship_user;

--
-- Name: system_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.system_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.system_settings_id_seq OWNER TO scholarship_user;

--
-- Name: system_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.system_settings_id_seq OWNED BY public.system_settings.id;


--
-- Name: user_profile_history; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.user_profile_history (
    id integer NOT NULL,
    user_id integer NOT NULL,
    field_name character varying(100) NOT NULL,
    old_value text,
    new_value text,
    change_reason character varying(255),
    changed_at timestamp with time zone,
    ip_address character varying(45),
    user_agent character varying(500)
);


ALTER TABLE public.user_profile_history OWNER TO scholarship_user;

--
-- Name: user_profile_history_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.user_profile_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.user_profile_history_id_seq OWNER TO scholarship_user;

--
-- Name: user_profile_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.user_profile_history_id_seq OWNED BY public.user_profile_history.id;


--
-- Name: user_profiles; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.user_profiles (
    id integer NOT NULL,
    user_id integer NOT NULL,
    bank_code character varying(20),
    account_number character varying(50),
    bank_document_photo_url character varying(500),
    bank_document_object_name character varying(500),
    advisor_name character varying(100),
    advisor_email character varying(100),
    advisor_nycu_id character varying(20),
    preferred_language character varying(10),
    custom_fields json,
    privacy_settings json,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);


ALTER TABLE public.user_profiles OWNER TO scholarship_user;

--
-- Name: user_profiles_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.user_profiles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.user_profiles_id_seq OWNER TO scholarship_user;

--
-- Name: user_profiles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.user_profiles_id_seq OWNED BY public.user_profiles.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: scholarship_user
--

CREATE TABLE public.users (
    id integer NOT NULL,
    nycu_id character varying(50) NOT NULL,
    name character varying(100) NOT NULL,
    email character varying(100),
    user_type public.usertype NOT NULL,
    status public.employeestatus,
    dept_code character varying(20),
    dept_name character varying(100),
    role public.userrole,
    comment character varying(255),
    last_login_at timestamp with time zone,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    raw_data json
);


ALTER TABLE public.users OWNER TO scholarship_user;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: scholarship_user
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.users_id_seq OWNER TO scholarship_user;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: scholarship_user
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: academies id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.academies ALTER COLUMN id SET DEFAULT nextval('public.academies_id_seq'::regclass);


--
-- Name: admin_scholarships id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.admin_scholarships ALTER COLUMN id SET DEFAULT nextval('public.admin_scholarships_id_seq'::regclass);


--
-- Name: application_documents id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.application_documents ALTER COLUMN id SET DEFAULT nextval('public.application_documents_id_seq'::regclass);


--
-- Name: application_fields id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.application_fields ALTER COLUMN id SET DEFAULT nextval('public.application_fields_id_seq'::regclass);


--
-- Name: application_files id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.application_files ALTER COLUMN id SET DEFAULT nextval('public.application_files_id_seq'::regclass);


--
-- Name: application_reviews id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.application_reviews ALTER COLUMN id SET DEFAULT nextval('public.application_reviews_id_seq'::regclass);


--
-- Name: applications id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.applications ALTER COLUMN id SET DEFAULT nextval('public.applications_id_seq'::regclass);


--
-- Name: audit_logs id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.audit_logs ALTER COLUMN id SET DEFAULT nextval('public.audit_logs_id_seq'::regclass);


--
-- Name: college_ranking_items id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.college_ranking_items ALTER COLUMN id SET DEFAULT nextval('public.college_ranking_items_id_seq'::regclass);


--
-- Name: college_rankings id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.college_rankings ALTER COLUMN id SET DEFAULT nextval('public.college_rankings_id_seq'::regclass);


--
-- Name: college_reviews id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.college_reviews ALTER COLUMN id SET DEFAULT nextval('public.college_reviews_id_seq'::regclass);


--
-- Name: configuration_audit_logs id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.configuration_audit_logs ALTER COLUMN id SET DEFAULT nextval('public.configuration_audit_logs_id_seq'::regclass);


--
-- Name: degrees id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.degrees ALTER COLUMN id SET DEFAULT nextval('public.degrees_id_seq'::regclass);


--
-- Name: departments id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.departments ALTER COLUMN id SET DEFAULT nextval('public.departments_id_seq'::regclass);


--
-- Name: email_templates id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.email_templates ALTER COLUMN id SET DEFAULT nextval('public.email_templates_id_seq'::regclass);


--
-- Name: identities id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.identities ALTER COLUMN id SET DEFAULT nextval('public.identities_id_seq'::regclass);


--
-- Name: notification_preferences id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notification_preferences ALTER COLUMN id SET DEFAULT nextval('public.notification_preferences_id_seq'::regclass);


--
-- Name: notification_queue id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notification_queue ALTER COLUMN id SET DEFAULT nextval('public.notification_queue_id_seq'::regclass);


--
-- Name: notification_reads id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notification_reads ALTER COLUMN id SET DEFAULT nextval('public.notification_reads_id_seq'::regclass);


--
-- Name: notification_templates id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notification_templates ALTER COLUMN id SET DEFAULT nextval('public.notification_templates_id_seq'::regclass);


--
-- Name: notifications id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notifications ALTER COLUMN id SET DEFAULT nextval('public.notifications_id_seq'::regclass);


--
-- Name: professor_review_items id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.professor_review_items ALTER COLUMN id SET DEFAULT nextval('public.professor_review_items_id_seq'::regclass);


--
-- Name: professor_reviews id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.professor_reviews ALTER COLUMN id SET DEFAULT nextval('public.professor_reviews_id_seq'::regclass);


--
-- Name: professor_student_relationships id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.professor_student_relationships ALTER COLUMN id SET DEFAULT nextval('public.professor_student_relationships_id_seq'::regclass);


--
-- Name: quota_distributions id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.quota_distributions ALTER COLUMN id SET DEFAULT nextval('public.quota_distributions_id_seq'::regclass);


--
-- Name: scholarship_configurations id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_configurations ALTER COLUMN id SET DEFAULT nextval('public.scholarship_configurations_id_seq'::regclass);


--
-- Name: scholarship_rules id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_rules ALTER COLUMN id SET DEFAULT nextval('public.scholarship_rules_id_seq'::regclass);


--
-- Name: scholarship_sub_type_configs id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_sub_type_configs ALTER COLUMN id SET DEFAULT nextval('public.scholarship_sub_type_configs_id_seq'::regclass);


--
-- Name: scholarship_types id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_types ALTER COLUMN id SET DEFAULT nextval('public.scholarship_types_id_seq'::regclass);


--
-- Name: school_identities id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.school_identities ALTER COLUMN id SET DEFAULT nextval('public.school_identities_id_seq'::regclass);


--
-- Name: studying_statuses id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.studying_statuses ALTER COLUMN id SET DEFAULT nextval('public.studying_statuses_id_seq'::regclass);


--
-- Name: system_settings id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.system_settings ALTER COLUMN id SET DEFAULT nextval('public.system_settings_id_seq'::regclass);


--
-- Name: user_profile_history id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.user_profile_history ALTER COLUMN id SET DEFAULT nextval('public.user_profile_history_id_seq'::regclass);


--
-- Name: user_profiles id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.user_profiles ALTER COLUMN id SET DEFAULT nextval('public.user_profiles_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: notification_reads _notification_user_read_uc; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notification_reads
    ADD CONSTRAINT _notification_user_read_uc UNIQUE (notification_id, user_id);


--
-- Name: notification_preferences _user_notification_type_uc; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notification_preferences
    ADD CONSTRAINT _user_notification_type_uc UNIQUE (user_id, notification_type);


--
-- Name: academies academies_code_key; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.academies
    ADD CONSTRAINT academies_code_key UNIQUE (code);


--
-- Name: academies academies_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.academies
    ADD CONSTRAINT academies_pkey PRIMARY KEY (id);


--
-- Name: admin_scholarships admin_scholarships_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.admin_scholarships
    ADD CONSTRAINT admin_scholarships_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: application_documents application_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.application_documents
    ADD CONSTRAINT application_documents_pkey PRIMARY KEY (id);


--
-- Name: application_fields application_fields_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.application_fields
    ADD CONSTRAINT application_fields_pkey PRIMARY KEY (id);


--
-- Name: application_files application_files_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.application_files
    ADD CONSTRAINT application_files_pkey PRIMARY KEY (id);


--
-- Name: application_reviews application_reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.application_reviews
    ADD CONSTRAINT application_reviews_pkey PRIMARY KEY (id);


--
-- Name: applications applications_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_pkey PRIMARY KEY (id);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: college_ranking_items college_ranking_items_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.college_ranking_items
    ADD CONSTRAINT college_ranking_items_pkey PRIMARY KEY (id);


--
-- Name: college_rankings college_rankings_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.college_rankings
    ADD CONSTRAINT college_rankings_pkey PRIMARY KEY (id);


--
-- Name: college_reviews college_reviews_application_id_key; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.college_reviews
    ADD CONSTRAINT college_reviews_application_id_key UNIQUE (application_id);


--
-- Name: college_reviews college_reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.college_reviews
    ADD CONSTRAINT college_reviews_pkey PRIMARY KEY (id);


--
-- Name: configuration_audit_logs configuration_audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.configuration_audit_logs
    ADD CONSTRAINT configuration_audit_logs_pkey PRIMARY KEY (id);


--
-- Name: degrees degrees_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.degrees
    ADD CONSTRAINT degrees_pkey PRIMARY KEY (id);


--
-- Name: departments departments_code_key; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_code_key UNIQUE (code);


--
-- Name: departments departments_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_pkey PRIMARY KEY (id);


--
-- Name: email_templates email_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.email_templates
    ADD CONSTRAINT email_templates_pkey PRIMARY KEY (id);


--
-- Name: identities identities_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.identities
    ADD CONSTRAINT identities_pkey PRIMARY KEY (id);


--
-- Name: notification_preferences notification_preferences_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notification_preferences
    ADD CONSTRAINT notification_preferences_pkey PRIMARY KEY (id);


--
-- Name: notification_queue notification_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notification_queue
    ADD CONSTRAINT notification_queue_pkey PRIMARY KEY (id);


--
-- Name: notification_reads notification_reads_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notification_reads
    ADD CONSTRAINT notification_reads_pkey PRIMARY KEY (id);


--
-- Name: notification_templates notification_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notification_templates
    ADD CONSTRAINT notification_templates_pkey PRIMARY KEY (id);


--
-- Name: notification_templates notification_templates_type_key; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notification_templates
    ADD CONSTRAINT notification_templates_type_key UNIQUE (type);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: professor_review_items professor_review_items_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.professor_review_items
    ADD CONSTRAINT professor_review_items_pkey PRIMARY KEY (id);


--
-- Name: professor_reviews professor_reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.professor_reviews
    ADD CONSTRAINT professor_reviews_pkey PRIMARY KEY (id);


--
-- Name: professor_student_relationships professor_student_relationships_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.professor_student_relationships
    ADD CONSTRAINT professor_student_relationships_pkey PRIMARY KEY (id);


--
-- Name: quota_distributions quota_distributions_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.quota_distributions
    ADD CONSTRAINT quota_distributions_pkey PRIMARY KEY (id);


--
-- Name: scholarship_configurations scholarship_configurations_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_configurations
    ADD CONSTRAINT scholarship_configurations_pkey PRIMARY KEY (id);


--
-- Name: scholarship_rules scholarship_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_rules
    ADD CONSTRAINT scholarship_rules_pkey PRIMARY KEY (id);


--
-- Name: scholarship_sub_type_configs scholarship_sub_type_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_sub_type_configs
    ADD CONSTRAINT scholarship_sub_type_configs_pkey PRIMARY KEY (id);


--
-- Name: scholarship_types scholarship_types_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_types
    ADD CONSTRAINT scholarship_types_pkey PRIMARY KEY (id);


--
-- Name: school_identities school_identities_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.school_identities
    ADD CONSTRAINT school_identities_pkey PRIMARY KEY (id);


--
-- Name: studying_statuses studying_statuses_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.studying_statuses
    ADD CONSTRAINT studying_statuses_pkey PRIMARY KEY (id);


--
-- Name: system_settings system_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.system_settings
    ADD CONSTRAINT system_settings_pkey PRIMARY KEY (id);


--
-- Name: admin_scholarships uq_admin_scholarship; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.admin_scholarships
    ADD CONSTRAINT uq_admin_scholarship UNIQUE (admin_id, scholarship_id);


--
-- Name: enroll_types uq_degree_code; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.enroll_types
    ADD CONSTRAINT uq_degree_code PRIMARY KEY ("degreeId", code);


--
-- Name: professor_student_relationships uq_prof_student_type; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.professor_student_relationships
    ADD CONSTRAINT uq_prof_student_type UNIQUE (professor_id, student_id, relationship_type);


--
-- Name: scholarship_configurations uq_scholarship_config_type_year_semester; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_configurations
    ADD CONSTRAINT uq_scholarship_config_type_year_semester UNIQUE (scholarship_type_id, academic_year, semester);


--
-- Name: applications uq_user_scholarship_academic_term; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT uq_user_scholarship_academic_term UNIQUE (user_id, scholarship_type_id, academic_year, semester);


--
-- Name: user_profile_history user_profile_history_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.user_profile_history
    ADD CONSTRAINT user_profile_history_pkey PRIMARY KEY (id);


--
-- Name: user_profiles user_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.user_profiles
    ADD CONSTRAINT user_profiles_pkey PRIMARY KEY (id);


--
-- Name: user_profiles user_profiles_user_id_key; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.user_profiles
    ADD CONSTRAINT user_profiles_user_id_key UNIQUE (user_id);


--
-- Name: users users_nycu_id_key; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_nycu_id_key UNIQUE (nycu_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_notifications_group_key; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX idx_notifications_group_key ON public.notifications USING btree (group_key, created_at);


--
-- Name: idx_notifications_priority_scheduled; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX idx_notifications_priority_scheduled ON public.notifications USING btree (priority, scheduled_for);


--
-- Name: idx_notifications_type_created; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX idx_notifications_type_created ON public.notifications USING btree (notification_type, created_at);


--
-- Name: idx_notifications_user_unread; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX idx_notifications_user_unread ON public.notifications USING btree (user_id, is_read, created_at);


--
-- Name: ix_application_documents_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_application_documents_id ON public.application_documents USING btree (id);


--
-- Name: ix_application_documents_scholarship_type; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_application_documents_scholarship_type ON public.application_documents USING btree (scholarship_type);


--
-- Name: ix_application_fields_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_application_fields_id ON public.application_fields USING btree (id);


--
-- Name: ix_application_fields_scholarship_type; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_application_fields_scholarship_type ON public.application_fields USING btree (scholarship_type);


--
-- Name: ix_application_files_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_application_files_id ON public.application_files USING btree (id);


--
-- Name: ix_application_reviews_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_application_reviews_id ON public.application_reviews USING btree (id);


--
-- Name: ix_applications_app_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE UNIQUE INDEX ix_applications_app_id ON public.applications USING btree (app_id);


--
-- Name: ix_applications_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_applications_id ON public.applications USING btree (id);


--
-- Name: ix_audit_logs_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_audit_logs_id ON public.audit_logs USING btree (id);


--
-- Name: ix_college_ranking_items_allocation; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_college_ranking_items_allocation ON public.college_ranking_items USING btree (is_allocated, status);


--
-- Name: ix_college_ranking_items_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_college_ranking_items_id ON public.college_ranking_items USING btree (id);


--
-- Name: ix_college_ranking_items_position; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_college_ranking_items_position ON public.college_ranking_items USING btree (ranking_id, rank_position);


--
-- Name: ix_college_ranking_items_score; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_college_ranking_items_score ON public.college_ranking_items USING btree (total_score DESC);


--
-- Name: ix_college_rankings_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_college_rankings_id ON public.college_rankings USING btree (id);


--
-- Name: ix_college_rankings_lookup; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_college_rankings_lookup ON public.college_rankings USING btree (scholarship_type_id, sub_type_code, academic_year, semester);


--
-- Name: ix_college_rankings_status_finalized; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_college_rankings_status_finalized ON public.college_rankings USING btree (ranking_status, is_finalized);


--
-- Name: ix_college_reviews_application_reviewer; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_college_reviews_application_reviewer ON public.college_reviews USING btree (application_id, reviewer_id);


--
-- Name: ix_college_reviews_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_college_reviews_id ON public.college_reviews USING btree (id);


--
-- Name: ix_college_reviews_priority_attention; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_college_reviews_priority_attention ON public.college_reviews USING btree (is_priority, needs_special_attention);


--
-- Name: ix_college_reviews_ranking_score; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_college_reviews_ranking_score ON public.college_reviews USING btree (ranking_score DESC);


--
-- Name: ix_college_reviews_recommendation_status; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_college_reviews_recommendation_status ON public.college_reviews USING btree (recommendation, review_status);


--
-- Name: ix_configuration_audit_logs_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_configuration_audit_logs_id ON public.configuration_audit_logs USING btree (id);


--
-- Name: ix_configuration_audit_logs_setting_key; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_configuration_audit_logs_setting_key ON public.configuration_audit_logs USING btree (setting_key);


--
-- Name: ix_email_templates_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_email_templates_id ON public.email_templates USING btree (id);


--
-- Name: ix_email_templates_key; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE UNIQUE INDEX ix_email_templates_key ON public.email_templates USING btree (key);


--
-- Name: ix_notification_preferences_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_notification_preferences_id ON public.notification_preferences USING btree (id);


--
-- Name: ix_notification_preferences_user_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_notification_preferences_user_id ON public.notification_preferences USING btree (user_id);


--
-- Name: ix_notification_queue_batch_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_notification_queue_batch_id ON public.notification_queue USING btree (batch_id);


--
-- Name: ix_notification_queue_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_notification_queue_id ON public.notification_queue USING btree (id);


--
-- Name: ix_notification_queue_scheduled_for; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_notification_queue_scheduled_for ON public.notification_queue USING btree (scheduled_for);


--
-- Name: ix_notification_queue_user_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_notification_queue_user_id ON public.notification_queue USING btree (user_id);


--
-- Name: ix_notification_reads_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_notification_reads_id ON public.notification_reads USING btree (id);


--
-- Name: ix_notification_templates_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_notification_templates_id ON public.notification_templates USING btree (id);


--
-- Name: ix_notifications_created_at; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_notifications_created_at ON public.notifications USING btree (created_at);


--
-- Name: ix_notifications_group_key; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_notifications_group_key ON public.notifications USING btree (group_key);


--
-- Name: ix_notifications_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_notifications_id ON public.notifications USING btree (id);


--
-- Name: ix_notifications_is_read; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_notifications_is_read ON public.notifications USING btree (is_read);


--
-- Name: ix_notifications_notification_type; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_notifications_notification_type ON public.notifications USING btree (notification_type);


--
-- Name: ix_notifications_priority; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_notifications_priority ON public.notifications USING btree (priority);


--
-- Name: ix_notifications_scheduled_for; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_notifications_scheduled_for ON public.notifications USING btree (scheduled_for);


--
-- Name: ix_notifications_user_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_notifications_user_id ON public.notifications USING btree (user_id);


--
-- Name: ix_professor_review_items_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_professor_review_items_id ON public.professor_review_items USING btree (id);


--
-- Name: ix_professor_reviews_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_professor_reviews_id ON public.professor_reviews USING btree (id);


--
-- Name: ix_professor_student_relationships_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_professor_student_relationships_id ON public.professor_student_relationships USING btree (id);


--
-- Name: ix_professor_student_relationships_professor_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_professor_student_relationships_professor_id ON public.professor_student_relationships USING btree (professor_id);


--
-- Name: ix_professor_student_relationships_student_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_professor_student_relationships_student_id ON public.professor_student_relationships USING btree (student_id);


--
-- Name: ix_quota_distributions_academic_year; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_quota_distributions_academic_year ON public.quota_distributions USING btree (academic_year, semester);


--
-- Name: ix_quota_distributions_execution; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_quota_distributions_execution ON public.quota_distributions USING btree (executed_at, executed_by);


--
-- Name: ix_quota_distributions_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_quota_distributions_id ON public.quota_distributions USING btree (id);


--
-- Name: ix_scholarship_configurations_academic_year; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_scholarship_configurations_academic_year ON public.scholarship_configurations USING btree (academic_year);


--
-- Name: ix_scholarship_configurations_config_code; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE UNIQUE INDEX ix_scholarship_configurations_config_code ON public.scholarship_configurations USING btree (config_code);


--
-- Name: ix_scholarship_configurations_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_scholarship_configurations_id ON public.scholarship_configurations USING btree (id);


--
-- Name: ix_scholarship_configurations_semester; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_scholarship_configurations_semester ON public.scholarship_configurations USING btree (semester);


--
-- Name: ix_scholarship_rules_academic_year; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_scholarship_rules_academic_year ON public.scholarship_rules USING btree (academic_year);


--
-- Name: ix_scholarship_rules_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_scholarship_rules_id ON public.scholarship_rules USING btree (id);


--
-- Name: ix_scholarship_rules_semester; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_scholarship_rules_semester ON public.scholarship_rules USING btree (semester);


--
-- Name: ix_scholarship_sub_type_configs_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_scholarship_sub_type_configs_id ON public.scholarship_sub_type_configs USING btree (id);


--
-- Name: ix_scholarship_types_code; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE UNIQUE INDEX ix_scholarship_types_code ON public.scholarship_types USING btree (code);


--
-- Name: ix_scholarship_types_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_scholarship_types_id ON public.scholarship_types USING btree (id);


--
-- Name: ix_system_settings_id; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE INDEX ix_system_settings_id ON public.system_settings USING btree (id);


--
-- Name: ix_system_settings_key; Type: INDEX; Schema: public; Owner: scholarship_user
--

CREATE UNIQUE INDEX ix_system_settings_key ON public.system_settings USING btree (key);


--
-- Name: admin_scholarships admin_scholarships_admin_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.admin_scholarships
    ADD CONSTRAINT admin_scholarships_admin_id_fkey FOREIGN KEY (admin_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: admin_scholarships admin_scholarships_scholarship_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.admin_scholarships
    ADD CONSTRAINT admin_scholarships_scholarship_id_fkey FOREIGN KEY (scholarship_id) REFERENCES public.scholarship_types(id) ON DELETE CASCADE;


--
-- Name: application_documents application_documents_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.application_documents
    ADD CONSTRAINT application_documents_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: application_documents application_documents_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.application_documents
    ADD CONSTRAINT application_documents_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: application_fields application_fields_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.application_fields
    ADD CONSTRAINT application_fields_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: application_fields application_fields_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.application_fields
    ADD CONSTRAINT application_fields_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: application_files application_files_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.application_files
    ADD CONSTRAINT application_files_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.applications(id);


--
-- Name: application_reviews application_reviews_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.application_reviews
    ADD CONSTRAINT application_reviews_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.applications(id);


--
-- Name: application_reviews application_reviews_reviewer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.application_reviews
    ADD CONSTRAINT application_reviews_reviewer_id_fkey FOREIGN KEY (reviewer_id) REFERENCES public.users(id);


--
-- Name: applications applications_final_approver_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_final_approver_id_fkey FOREIGN KEY (final_approver_id) REFERENCES public.users(id);


--
-- Name: applications applications_previous_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_previous_application_id_fkey FOREIGN KEY (previous_application_id) REFERENCES public.applications(id);


--
-- Name: applications applications_professor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_professor_id_fkey FOREIGN KEY (professor_id) REFERENCES public.users(id);


--
-- Name: applications applications_reviewer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_reviewer_id_fkey FOREIGN KEY (reviewer_id) REFERENCES public.users(id);


--
-- Name: applications applications_scholarship_configuration_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_scholarship_configuration_id_fkey FOREIGN KEY (scholarship_configuration_id) REFERENCES public.scholarship_configurations(id);


--
-- Name: applications applications_scholarship_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_scholarship_type_id_fkey FOREIGN KEY (scholarship_type_id) REFERENCES public.scholarship_types(id);


--
-- Name: applications applications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: audit_logs audit_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: college_ranking_items college_ranking_items_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.college_ranking_items
    ADD CONSTRAINT college_ranking_items_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.applications(id);


--
-- Name: college_ranking_items college_ranking_items_college_review_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.college_ranking_items
    ADD CONSTRAINT college_ranking_items_college_review_id_fkey FOREIGN KEY (college_review_id) REFERENCES public.college_reviews(id);


--
-- Name: college_ranking_items college_ranking_items_ranking_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.college_ranking_items
    ADD CONSTRAINT college_ranking_items_ranking_id_fkey FOREIGN KEY (ranking_id) REFERENCES public.college_rankings(id);


--
-- Name: college_rankings college_rankings_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.college_rankings
    ADD CONSTRAINT college_rankings_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: college_rankings college_rankings_finalized_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.college_rankings
    ADD CONSTRAINT college_rankings_finalized_by_fkey FOREIGN KEY (finalized_by) REFERENCES public.users(id);


--
-- Name: college_rankings college_rankings_scholarship_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.college_rankings
    ADD CONSTRAINT college_rankings_scholarship_type_id_fkey FOREIGN KEY (scholarship_type_id) REFERENCES public.scholarship_types(id);


--
-- Name: college_reviews college_reviews_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.college_reviews
    ADD CONSTRAINT college_reviews_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.applications(id);


--
-- Name: college_reviews college_reviews_reviewer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.college_reviews
    ADD CONSTRAINT college_reviews_reviewer_id_fkey FOREIGN KEY (reviewer_id) REFERENCES public.users(id);


--
-- Name: configuration_audit_logs configuration_audit_logs_changed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.configuration_audit_logs
    ADD CONSTRAINT configuration_audit_logs_changed_by_fkey FOREIGN KEY (changed_by) REFERENCES public.users(id);


--
-- Name: enroll_types enroll_types_degreeId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.enroll_types
    ADD CONSTRAINT "enroll_types_degreeId_fkey" FOREIGN KEY ("degreeId") REFERENCES public.degrees(id);


--
-- Name: notification_preferences notification_preferences_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notification_preferences
    ADD CONSTRAINT notification_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: notification_queue notification_queue_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notification_queue
    ADD CONSTRAINT notification_queue_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: notification_reads notification_reads_notification_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notification_reads
    ADD CONSTRAINT notification_reads_notification_id_fkey FOREIGN KEY (notification_id) REFERENCES public.notifications(id) ON DELETE CASCADE;


--
-- Name: notification_reads notification_reads_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notification_reads
    ADD CONSTRAINT notification_reads_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: professor_review_items professor_review_items_review_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.professor_review_items
    ADD CONSTRAINT professor_review_items_review_id_fkey FOREIGN KEY (review_id) REFERENCES public.professor_reviews(id);


--
-- Name: professor_reviews professor_reviews_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.professor_reviews
    ADD CONSTRAINT professor_reviews_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.applications(id);


--
-- Name: professor_reviews professor_reviews_professor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.professor_reviews
    ADD CONSTRAINT professor_reviews_professor_id_fkey FOREIGN KEY (professor_id) REFERENCES public.users(id);


--
-- Name: professor_student_relationships professor_student_relationships_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.professor_student_relationships
    ADD CONSTRAINT professor_student_relationships_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: professor_student_relationships professor_student_relationships_professor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.professor_student_relationships
    ADD CONSTRAINT professor_student_relationships_professor_id_fkey FOREIGN KEY (professor_id) REFERENCES public.users(id);


--
-- Name: professor_student_relationships professor_student_relationships_student_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.professor_student_relationships
    ADD CONSTRAINT professor_student_relationships_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.users(id);


--
-- Name: quota_distributions quota_distributions_executed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.quota_distributions
    ADD CONSTRAINT quota_distributions_executed_by_fkey FOREIGN KEY (executed_by) REFERENCES public.users(id);


--
-- Name: scholarship_configurations scholarship_configurations_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_configurations
    ADD CONSTRAINT scholarship_configurations_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: scholarship_configurations scholarship_configurations_previous_config_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_configurations
    ADD CONSTRAINT scholarship_configurations_previous_config_id_fkey FOREIGN KEY (previous_config_id) REFERENCES public.scholarship_configurations(id);


--
-- Name: scholarship_configurations scholarship_configurations_scholarship_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_configurations
    ADD CONSTRAINT scholarship_configurations_scholarship_type_id_fkey FOREIGN KEY (scholarship_type_id) REFERENCES public.scholarship_types(id);


--
-- Name: scholarship_configurations scholarship_configurations_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_configurations
    ADD CONSTRAINT scholarship_configurations_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: scholarship_rules scholarship_rules_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_rules
    ADD CONSTRAINT scholarship_rules_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: scholarship_rules scholarship_rules_scholarship_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_rules
    ADD CONSTRAINT scholarship_rules_scholarship_type_id_fkey FOREIGN KEY (scholarship_type_id) REFERENCES public.scholarship_types(id);


--
-- Name: scholarship_rules scholarship_rules_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_rules
    ADD CONSTRAINT scholarship_rules_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: scholarship_sub_type_configs scholarship_sub_type_configs_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_sub_type_configs
    ADD CONSTRAINT scholarship_sub_type_configs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: scholarship_sub_type_configs scholarship_sub_type_configs_scholarship_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_sub_type_configs
    ADD CONSTRAINT scholarship_sub_type_configs_scholarship_type_id_fkey FOREIGN KEY (scholarship_type_id) REFERENCES public.scholarship_types(id);


--
-- Name: scholarship_sub_type_configs scholarship_sub_type_configs_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_sub_type_configs
    ADD CONSTRAINT scholarship_sub_type_configs_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: scholarship_types scholarship_types_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_types
    ADD CONSTRAINT scholarship_types_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: scholarship_types scholarship_types_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.scholarship_types
    ADD CONSTRAINT scholarship_types_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: system_settings system_settings_last_modified_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.system_settings
    ADD CONSTRAINT system_settings_last_modified_by_fkey FOREIGN KEY (last_modified_by) REFERENCES public.users(id);


--
-- Name: user_profile_history user_profile_history_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.user_profile_history
    ADD CONSTRAINT user_profile_history_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_profiles user_profiles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: scholarship_user
--

ALTER TABLE ONLY public.user_profiles
    ADD CONSTRAINT user_profiles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

