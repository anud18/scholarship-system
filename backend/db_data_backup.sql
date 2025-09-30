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
-- Data for Name: academies; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.academies (id, code, name) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.users (id, nycu_id, name, email, user_type, status, dept_code, dept_name, role, comment, last_login_at, created_at, updated_at, raw_data) FROM stdin;
1	admin	系統管理員	admin@nycu.edu.tw	employee	在職	9000	教務處	admin	\N	\N	2025-09-27 15:27:54.134851+00	2025-09-27 15:28:35.614349+00	\N
4	super_admin	超級管理員	super_admin@nycu.edu.tw	employee	在職	9000	教務處	super_admin	\N	\N	2025-09-27 15:28:35.614349+00	2025-09-27 15:28:35.614349+00	\N
5	professor	李教授	professor@nycu.edu.tw	employee	在職	7000	資訊學院	professor	\N	\N	2025-09-27 15:28:35.614349+00	2025-09-27 15:28:35.614349+00	\N
6	college	學院審核員	college@nycu.edu.tw	employee	在職	7000	資訊學院	college	\N	\N	2025-09-27 15:28:35.614349+00	2025-09-27 15:28:35.614349+00	\N
7	stu_under	陳小明	stu_under@nycu.edu.tw	student	在學	CS	資訊工程學系	student	\N	\N	2025-09-27 15:28:35.614349+00	2025-09-27 15:28:35.614349+00	\N
8	stu_phd	王博士	stu_phd@nycu.edu.tw	student	在學	CS	資訊工程學系	student	\N	\N	2025-09-27 15:28:35.614349+00	2025-09-27 15:28:35.614349+00	\N
9	stu_direct	李逕升	stu_direct@nycu.edu.tw	student	在學	CS	資訊工程學系	student	\N	\N	2025-09-27 15:28:35.614349+00	2025-09-27 15:28:35.614349+00	\N
10	stu_master	張碩士	stu_master@nycu.edu.tw	student	在學	CS	資訊工程學系	student	\N	\N	2025-09-27 15:28:35.614349+00	2025-09-27 15:28:35.614349+00	\N
11	phd_china	陸生	phd_china@nycu.edu.tw	student	在學	CS	資訊工程學系	student	\N	\N	2025-09-27 15:28:35.614349+00	2025-09-27 15:28:35.614349+00	\N
12	cs_professor	李資訊教授	cs_professor@nycu.edu.tw	employee	在職	CS	資訊工程學系	professor	\N	\N	2025-09-27 15:28:35.614349+00	2025-09-27 15:28:35.614349+00	\N
13	cs_college	資訊學院審核員	cs_college@nycu.edu.tw	employee	在職	CS	資訊工程學系	college	\N	\N	2025-09-27 15:28:35.614349+00	2025-09-27 15:28:35.614349+00	\N
14	cs_phd001	王博士研究生	cs_phd001@nycu.edu.tw	student	在學	CS	資訊工程學系	student	\N	\N	2025-09-27 15:28:35.614349+00	2025-09-27 15:28:35.614349+00	\N
15	cs_phd002	陳AI博士	cs_phd002@nycu.edu.tw	student	在學	CS	資訊工程學系	student	\N	\N	2025-09-27 15:28:35.614349+00	2025-09-27 15:28:35.614349+00	\N
16	cs_phd003	林機器學習博士	cs_phd003@nycu.edu.tw	student	在學	CS	資訊工程學系	student	\N	\N	2025-09-27 15:28:35.614349+00	2025-09-27 15:28:35.614349+00	\N
17	test001	測試學生一	test.student1@example.com	student	在學	EE	電機工程學系	student	\N	2025-09-28 04:53:14.464324+00	2025-09-28 04:53:14.585317+00	2025-09-28 04:53:14.464362+00	\N
18	test002	測試學生二	test.student2@example.com	student	在學	EE	電機工程學系	student	\N	2025-09-28 04:53:14.464324+00	2025-09-28 04:53:14.591286+00	2025-09-28 04:53:14.464362+00	\N
19	test003	測試學生三	test.student3@example.com	student	在學	CS	資訊工程學系	student	\N	2025-09-28 04:53:14.464324+00	2025-09-28 04:53:14.594438+00	2025-09-28 04:53:14.464362+00	\N
20	admin001	測試管理員	test.admin@example.com	employee	在職	ADMIN	管理處	admin	\N	2025-09-28 04:53:14.464324+00	2025-09-28 04:53:14.597327+00	2025-09-28 04:53:14.464362+00	\N
\.


--
-- Data for Name: scholarship_types; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.scholarship_types (id, code, name, name_en, description, description_en, category, sub_type_list, sub_type_selection_mode, application_cycle, whitelist_enabled, status, created_at, updated_at, created_by, updated_by) FROM stdin;
1	undergraduate_freshman	學士班新生獎學金	Undergraduate Freshman Scholarship	適用於學士班新生 白名單 與 地區劃分	For undergraduate freshmen, white list and regional	undergraduate_freshman	\N	single	semester	f	active	2025-09-27 15:28:35.652183+00	2025-09-27 15:28:35.652183+00	\N	\N
2	phd	博士生獎學金	PhD Scholarship	適用於一般博士生，需完整研究計畫和教授推薦	For regular PhD students, requires complete research plan	phd	["nstc", "moe_1w", "moe_2w"]	hierarchical	yearly	f	active	2025-09-27 15:28:35.652183+00	2025-09-27 15:28:35.652183+00	\N	\N
3	direct_phd	逕讀博士獎學金	Direct PhD Scholarship	適用於逕讀博士班學生，需完整研究計畫	For direct PhD students, requires complete research plan	direct_phd	\N	single	yearly	f	active	2025-09-27 15:28:35.652183+00	2025-09-27 15:28:35.652183+00	\N	\N
4	test_phd_2025	測試博士班獎學金	\N	用於測試造冊系統的博士班獎學金	\N	phd	["GENERAL"]	single	semester	f	active	2025-09-28 04:52:22.276151+00	2025-09-28 04:52:22.273795+00	\N	\N
\.


--
-- Data for Name: admin_scholarships; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.admin_scholarships (id, admin_id, scholarship_id, assigned_at) FROM stdin;
\.


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.alembic_version (version_num) FROM stdin;
887d0765bce6
\.


--
-- Data for Name: application_documents; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.application_documents (id, scholarship_type, document_name, document_name_en, description, description_en, is_required, accepted_file_types, max_file_size, max_file_count, display_order, is_active, upload_instructions, upload_instructions_en, validation_rules, created_at, updated_at, created_by, updated_by) FROM stdin;
\.


--
-- Data for Name: application_fields; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.application_fields (id, scholarship_type, field_name, field_label, field_label_en, field_type, is_required, placeholder, placeholder_en, max_length, min_value, max_value, step_value, field_options, display_order, is_active, help_text, help_text_en, validation_rules, conditional_rules, created_at, updated_at, created_by, updated_by) FROM stdin;
\.


--
-- Data for Name: scholarship_configurations; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.scholarship_configurations (id, scholarship_type_id, academic_year, semester, config_name, config_code, description, description_en, has_quota_limit, has_college_quota, quota_management_mode, total_quota, quotas, amount, currency, whitelist_student_ids, renewal_application_start_date, renewal_application_end_date, application_start_date, application_end_date, renewal_professor_review_start, renewal_professor_review_end, renewal_college_review_start, renewal_college_review_end, requires_professor_recommendation, professor_review_start, professor_review_end, requires_college_review, college_review_start, college_review_end, review_deadline, is_active, effective_start_date, effective_end_date, version, previous_config_id, created_at, updated_at, created_by, updated_by) FROM stdin;
1	4	113	first	測試博士班配置	test_phd_2025_113_1	113學年度第一學期博士班獎學金配置	\N	f	f	none	\N	\N	50000	TWD	{}	\N	\N	2024-12-01 00:00:00+00	2025-02-28 00:00:00+00	\N	\N	\N	\N	t	\N	\N	t	\N	\N	\N	t	\N	\N	1.0	\N	2025-09-28 04:52:22.286745+00	2025-09-28 04:52:22.281273+00	\N	\N
\.


--
-- Data for Name: applications; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.applications (id, app_id, user_id, scholarship_type_id, scholarship_configuration_id, scholarship_name, amount, scholarship_subtype_list, sub_type_selection_mode, main_scholarship_type, sub_scholarship_type, is_renewal, previous_application_id, priority_score, review_deadline, decision_date, status, status_name, academic_year, semester, student_data, submitted_form_data, agree_terms, professor_id, reviewer_id, final_approver_id, review_score, review_comments, rejection_reason, college_ranking_score, final_ranking_position, quota_allocation_status, submitted_at, reviewed_at, approved_at, created_at, updated_at, meta_data) FROM stdin;
1	APP-2025-000001	17	4	1	測試博士班配置	50000.00	["GENERAL"]	single	PHD	GENERAL	f	\N	0	\N	\N	approved	\N	113	first	{"student_id": "A123456789", "name": "\\u6e2c\\u8a66\\u5b78\\u751f\\u4e00", "department": "\\u96fb\\u6a5f\\u5de5\\u7a0b\\u5b78\\u7cfb", "grade": "\\u535a\\u58eb\\u73ed\\u4e8c\\u5e74\\u7d1a", "gpa": 3.8, "email": "test.student1@example.com", "phone": "0912-345670", "address": "\\u53f0\\u5317\\u5e02\\u5927\\u5b89\\u5340\\u6e2c\\u8a66\\u8def1\\u865f", "bank_account": "123456780", "bank_code": "012", "bank_name": "\\u53f0\\u7063\\u9280\\u884c"}	\N	t	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2025-09-28 04:53:48.125084+00	2025-09-28 04:53:48.108869+00	\N
2	APP-2025-000002	18	4	1	測試博士班配置	50000.00	["GENERAL"]	single	PHD	GENERAL	f	\N	0	\N	\N	approved	\N	113	first	{"student_id": "B234567890", "name": "\\u6e2c\\u8a66\\u5b78\\u751f\\u4e8c", "department": "\\u96fb\\u6a5f\\u5de5\\u7a0b\\u5b78\\u7cfb", "grade": "\\u535a\\u58eb\\u73ed\\u4e8c\\u5e74\\u7d1a", "gpa": 3.6, "email": "test.student2@example.com", "phone": "0912-345671", "address": "\\u53f0\\u5317\\u5e02\\u5927\\u5b89\\u5340\\u6e2c\\u8a66\\u8def2\\u865f", "bank_account": "123456781", "bank_code": "012", "bank_name": "\\u53f0\\u7063\\u9280\\u884c"}	\N	t	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2025-09-28 04:53:48.137331+00	2025-09-28 04:53:48.131633+00	\N
3	APP-2025-000003	19	4	1	測試博士班配置	50000.00	["GENERAL"]	single	PHD	GENERAL	f	\N	0	\N	\N	approved	\N	113	first	{"student_id": "C345678901", "name": "\\u6e2c\\u8a66\\u5b78\\u751f\\u4e09", "department": "\\u8cc7\\u8a0a\\u5de5\\u7a0b\\u5b78\\u7cfb", "grade": "\\u535a\\u58eb\\u73ed\\u4e8c\\u5e74\\u7d1a", "gpa": 3.9, "email": "test.student3@example.com", "phone": "0912-345672", "address": "\\u53f0\\u5317\\u5e02\\u5927\\u5b89\\u5340\\u6e2c\\u8a66\\u8def3\\u865f", "bank_account": "123456782", "bank_code": "012", "bank_name": "\\u53f0\\u7063\\u9280\\u884c"}	\N	t	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	2025-09-28 04:53:48.143483+00	2025-09-28 04:53:48.140105+00	\N
\.


--
-- Data for Name: application_files; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.application_files (id, application_id, filename, original_filename, object_name, file_size, mime_type, content_type, file_type, ocr_processed, ocr_text, ocr_confidence, is_verified, verification_notes, uploaded_at, upload_date, processed_at) FROM stdin;
\.


--
-- Data for Name: application_reviews; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.application_reviews (id, application_id, reviewer_id, review_stage, review_status, score, comments, recommendation, decision_reason, criteria_scores, assigned_at, reviewed_at, due_date) FROM stdin;
\.


--
-- Data for Name: audit_logs; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.audit_logs (id, user_id, action, resource_type, resource_id, resource_name, description, old_values, new_values, ip_address, user_agent, request_method, request_url, request_headers, status, error_message, response_time_ms, created_at, trace_id, session_id, meta_data) FROM stdin;
\.


--
-- Data for Name: college_rankings; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.college_rankings (id, scholarship_type_id, sub_type_code, academic_year, semester, ranking_name, total_applications, total_quota, allocated_count, is_finalized, ranking_status, distribution_executed, distribution_date, github_issue_url, created_at, updated_at, finalized_at, created_by, finalized_by) FROM stdin;
\.


--
-- Data for Name: college_reviews; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.college_reviews (id, application_id, reviewer_id, ranking_score, academic_score, professor_review_score, college_criteria_score, special_circumstances_score, review_comments, recommendation, decision_reason, preliminary_rank, final_rank, sub_type_group, review_status, is_priority, needs_special_attention, scoring_weights, review_started_at, reviewed_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: college_ranking_items; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.college_ranking_items (id, ranking_id, application_id, college_review_id, rank_position, is_allocated, allocation_reason, total_score, tie_breaker_applied, tie_breaker_reason, status, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: configuration_audit_logs; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.configuration_audit_logs (id, setting_key, old_value, new_value, action, changed_by, change_reason, changed_at) FROM stdin;
\.


--
-- Data for Name: degrees; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.degrees (id, name) FROM stdin;
1	學士
2	碩士
3	博士
\.


--
-- Data for Name: departments; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.departments (id, code, name) FROM stdin;
\.


--
-- Data for Name: email_templates; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.email_templates (id, key, subject_template, body_template, cc, bcc, sending_type, recipient_options, requires_approval, max_recipients, updated_at) FROM stdin;
\.


--
-- Data for Name: email_history; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.email_history (id, recipient_email, cc_emails, bcc_emails, subject, body, template_key, email_category, application_id, scholarship_type_id, sent_by_user_id, sent_by_system, status, error_message, sent_at, retry_count, email_size_bytes) FROM stdin;
\.


--
-- Data for Name: enroll_types; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.enroll_types ("degreeId", code, name, name_en) FROM stdin;
\.


--
-- Data for Name: identities; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.identities (id, name) FROM stdin;
\.


--
-- Data for Name: notification_preferences; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.notification_preferences (id, user_id, notification_type, in_app_enabled, email_enabled, sms_enabled, push_enabled, frequency, quiet_hours_start, quiet_hours_end, timezone, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: notification_queue; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.notification_queue (id, user_id, batch_id, notification_type, priority, notifications_data, aggregated_content, scheduled_for, attempts, max_attempts, status, error_message, created_at, processed_at) FROM stdin;
\.


--
-- Data for Name: notifications; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.notifications (id, user_id, title, title_en, message, message_en, notification_type, priority, channel, data, href, related_resource_type, related_resource_id, action_url, meta_data, is_read, is_dismissed, is_archived, is_hidden, send_email, email_sent, email_sent_at, group_key, batch_id, scheduled_at, scheduled_for, expires_at, read_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: notification_reads; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.notification_reads (id, notification_id, user_id, is_read, read_at, created_at) FROM stdin;
\.


--
-- Data for Name: notification_templates; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.notification_templates (id, type, title_template, title_template_en, message_template, message_template_en, href_template, default_channels, default_priority, variables, is_active, requires_user_action, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: payment_rosters; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.payment_rosters (id, roster_code, scholarship_configuration_id, period_label, academic_year, roster_cycle, status, trigger_type, created_by, started_at, completed_at, locked_at, locked_by, total_applications, qualified_count, disqualified_count, total_amount, excel_filename, excel_file_path, excel_file_size, excel_file_hash, student_verification_enabled, verification_api_failures, notes, processing_log, created_at, updated_at) FROM stdin;
5	ROSTER-113-2025-01-test_phd_2025_113_1	1	2025-01	113	monthly	completed	manual	1	2025-09-28 05:11:42.881008+00	2025-09-28 05:11:42.913206+00	\N	\N	3	2	1	100000.00	\N	\N	\N	\N	t	0	\N	\N	2025-09-28 05:11:42.876938+00	2025-09-28 05:11:42.876938+00
\.


--
-- Data for Name: payment_roster_items; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.payment_roster_items (id, roster_id, application_id, student_id_number, student_name, student_email, bank_account, bank_code, bank_name, permanent_address, mailing_address, scholarship_name, scholarship_amount, scholarship_subtype, verification_status, verification_message, verification_at, verification_snapshot, is_included, exclusion_reason, excel_row_data, excel_remarks, nationality_code, residence_days_over_183, created_at, updated_at, rule_validation_result, failed_rules, warning_rules) FROM stdin;
4	5	1	A123456789	測試學生一	test.student1@example.com	123456780	012	台灣銀行	台北市大安區測試路1號	台北市大安區測試路1號	測試博士班獎學金	50000.00	GENERAL	withdrawn	學生已退學	2025-09-28 05:11:42.901851+00	{"status": "withdrawn", "message": "\\u5b78\\u751f\\u5df2\\u9000\\u5b78", "student_info": {"student_id": "A123456789", "name": "\\u6e2c\\u8a66\\u5b78\\u751f\\u4e00", "withdrawal_date": "2024-01-15", "withdrawal_reason": "\\u5fd7\\u8da3\\u4e0d\\u7b26"}, "verified_at": "2025-09-28T13:11:42.889369", "api_response": {"mock": true, "last_digit": 9}}	f	學籍驗證未通過: withdrawn	\N	\N	1	是	2025-09-28 05:11:42.876938+00	2025-09-28 05:11:42.876938+00	{"is_eligible": true, "failed_rules": [], "warning_rules": [], "details": {"no_rules_found": true}}	[]	[]
5	5	2	B234567890	測試學生二	測試學生二@m00.nycu.edu.tw	123456780	012	台灣銀行	新竹市大學路1000號	新竹市大學路1000號	測試博士班獎學金	50000.00	GENERAL	verified	學籍驗證通過	2025-09-28 05:11:42.908769+00	{"status": "verified", "message": "\\u5b78\\u7c4d\\u9a57\\u8b49\\u901a\\u904e", "student_info": {"student_id": "B234567890", "name": "\\u6e2c\\u8a66\\u5b78\\u751f\\u4e8c", "school_code": "NCTU", "school_name": "\\u570b\\u7acb\\u967d\\u660e\\u4ea4\\u901a\\u5927\\u5b78", "department": "\\u8cc7\\u8a0a\\u5de5\\u7a0b\\u5b78\\u7cfb", "grade": "\\u535a\\u58eb\\u73ed\\u4e8c\\u5e74\\u7d1a", "enrollment_status": "\\u5728\\u5b78", "enrollment_date": "2022-09-01", "gpa": 3.5, "email": "\\u6e2c\\u8a66\\u5b78\\u751f\\u4e8c@m00.nycu.edu.tw", "phone": "0912-000000", "address": "\\u65b0\\u7af9\\u5e02\\u5927\\u5b78\\u8def1000\\u865f", "bank_account": "123456780", "bank_code": "012", "bank_name": "\\u53f0\\u7063\\u9280\\u884c"}, "verified_at": "2025-09-28T13:11:42.902016", "api_response": {"mock": true, "last_digit": 0}}	t	\N	\N	\N	1	是	2025-09-28 05:11:42.876938+00	2025-09-28 05:11:42.876938+00	{"is_eligible": true, "failed_rules": [], "warning_rules": [], "details": {"no_rules_found": true}}	[]	[]
6	5	3	C345678901	測試學生三	測試學生三@m01.nycu.edu.tw	123456781	012	台灣銀行	新竹市大學路1001號	新竹市大學路1001號	測試博士班獎學金	50000.00	GENERAL	verified	學籍驗證通過	2025-09-28 05:11:42.913082+00	{"status": "verified", "message": "\\u5b78\\u7c4d\\u9a57\\u8b49\\u901a\\u904e", "student_info": {"student_id": "C345678901", "name": "\\u6e2c\\u8a66\\u5b78\\u751f\\u4e09", "school_code": "NCTU", "school_name": "\\u570b\\u7acb\\u967d\\u660e\\u4ea4\\u901a\\u5927\\u5b78", "department": "\\u8cc7\\u8a0a\\u5de5\\u7a0b\\u5b78\\u7cfb", "grade": "\\u535a\\u58eb\\u73ed\\u4e8c\\u5e74\\u7d1a", "enrollment_status": "\\u5728\\u5b78", "enrollment_date": "2022-09-01", "gpa": 3.6, "email": "\\u6e2c\\u8a66\\u5b78\\u751f\\u4e09@m01.nycu.edu.tw", "phone": "0912-001001", "address": "\\u65b0\\u7af9\\u5e02\\u5927\\u5b78\\u8def1001\\u865f", "bank_account": "123456781", "bank_code": "012", "bank_name": "\\u53f0\\u7063\\u9280\\u884c"}, "verified_at": "2025-09-28T13:11:42.908915", "api_response": {"mock": true, "last_digit": 1}}	t	\N	\N	\N	1	是	2025-09-28 05:11:42.876938+00	2025-09-28 05:11:42.876938+00	{"is_eligible": true, "failed_rules": [], "warning_rules": [], "details": {"no_rules_found": true}}	[]	[]
\.


--
-- Data for Name: professor_reviews; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.professor_reviews (id, application_id, professor_id, recommendation, review_status, reviewed_at, created_at) FROM stdin;
\.


--
-- Data for Name: professor_review_items; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.professor_review_items (id, review_id, sub_type_code, is_recommended, comments, created_at) FROM stdin;
\.


--
-- Data for Name: professor_student_relationships; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.professor_student_relationships (id, professor_id, student_id, relationship_type, department, academic_year, semester, is_active, can_view_applications, can_upload_documents, can_review_applications, created_at, updated_at, created_by, notes) FROM stdin;
1	5	8	advisor	資訊工程學系	113	first	t	t	t	t	2025-09-27 15:28:35.643467+00	2025-09-27 15:28:35.643467+00	\N	PhD advisor relationship
2	5	7	supervisor	資訊工程學系	113	first	t	t	f	f	2025-09-27 15:28:35.643467+00	2025-09-27 15:28:35.643467+00	\N	Undergraduate project supervisor
\.


--
-- Data for Name: quota_distributions; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.quota_distributions (id, distribution_name, academic_year, semester, total_applications, total_quota, total_allocated, algorithm_version, scoring_weights, distribution_rules, distribution_summary, exceptions, github_issue_number, github_issue_url, executed_at, executed_by) FROM stdin;
\.


--
-- Data for Name: roster_audit_logs; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.roster_audit_logs (id, roster_id, action, level, user_id, user_name, user_role, client_ip, user_agent, title, description, old_values, new_values, api_endpoint, request_method, request_payload, response_status, processing_time_ms, affected_items_count, error_code, error_message, warning_message, audit_metadata, tags, created_at) FROM stdin;
10	5	create	info	1	\N	\N	\N	\N	開始產生造冊 ROSTER-113-2025-01-test_phd_2025_113_1	\N	null	null	\N	\N	null	\N	\N	0	\N	\N	\N	null	null	2025-09-28 05:11:42.876938+00
11	5	item_update	info	1	\N	\N	\N	\N	更新申請 2 的學生資料 (更新欄位: department, gpa, email, phone, address, bank_account)	\N	null	null	\N	\N	null	\N	\N	0	\N	\N	\N	{"application_id": 2, "updated_fields": ["department", "gpa", "email", "phone", "address", "bank_account"], "old_data": {"department": "\\u8cc7\\u8a0a\\u5de5\\u7a0b\\u5b78\\u7cfb", "gpa": 3.5, "email": "\\u6e2c\\u8a66\\u5b78\\u751f\\u4e8c@m00.nycu.edu.tw", "phone": "0912-000000", "address": "\\u65b0\\u7af9\\u5e02\\u5927\\u5b78\\u8def1000\\u865f", "bank_account": "123456780"}, "new_data": {"department": "\\u8cc7\\u8a0a\\u5de5\\u7a0b\\u5b78\\u7cfb", "gpa": 3.5, "email": "\\u6e2c\\u8a66\\u5b78\\u751f\\u4e8c@m00.nycu.edu.tw", "phone": "0912-000000", "address": "\\u65b0\\u7af9\\u5e02\\u5927\\u5b78\\u8def1000\\u865f", "bank_account": "123456780"}, "verification_status": "verified", "verification_message": "\\u5b78\\u7c4d\\u9a57\\u8b49\\u901a\\u904e"}	null	2025-09-28 05:11:42.876938+00
12	5	item_update	info	1	\N	\N	\N	\N	更新申請 3 的學生資料 (更新欄位: gpa, email, phone, address, bank_account)	\N	null	null	\N	\N	null	\N	\N	0	\N	\N	\N	{"application_id": 3, "updated_fields": ["gpa", "email", "phone", "address", "bank_account"], "old_data": {"gpa": 3.6, "email": "\\u6e2c\\u8a66\\u5b78\\u751f\\u4e09@m01.nycu.edu.tw", "phone": "0912-001001", "address": "\\u65b0\\u7af9\\u5e02\\u5927\\u5b78\\u8def1001\\u865f", "bank_account": "123456781"}, "new_data": {"gpa": 3.6, "email": "\\u6e2c\\u8a66\\u5b78\\u751f\\u4e09@m01.nycu.edu.tw", "phone": "0912-001001", "address": "\\u65b0\\u7af9\\u5e02\\u5927\\u5b78\\u8def1001\\u865f", "bank_account": "123456781"}, "verification_status": "verified", "verification_message": "\\u5b78\\u7c4d\\u9a57\\u8b49\\u901a\\u904e"}	null	2025-09-28 05:11:42.876938+00
13	5	status_change	info	1	\N	\N	\N	\N	造冊產生完成: 合格2人, 不合格1人, 總金額$100000.00	\N	null	null	\N	\N	null	\N	\N	0	\N	\N	\N	{"qualified_count": 2, "disqualified_count": 1, "total_amount": 100000.0, "verification_failures": 0}	null	2025-09-28 05:11:42.876938+00
\.


--
-- Data for Name: roster_schedules; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.roster_schedules (id, scholarship_configuration_id, schedule_name, is_enabled, cron_expression, timezone, retry_count, retry_delay_minutes, notify_on_success, notify_on_failure, notification_emails, student_verification_enabled, auto_lock_after_completion, max_execution_time_minutes, created_by, created_at, updated_at, last_run_at, last_run_status, last_run_roster_id, next_run_at) FROM stdin;
\.


--
-- Data for Name: scheduled_emails; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.scheduled_emails (id, recipient_email, cc_emails, bcc_emails, subject, body, template_key, email_category, scheduled_for, status, application_id, scholarship_type_id, requires_approval, approved_by_user_id, approved_at, approval_notes, created_by_user_id, created_at, updated_at, retry_count, last_error, priority) FROM stdin;
\.


--
-- Data for Name: scholarship_rules; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.scholarship_rules (id, scholarship_type_id, sub_type, academic_year, semester, is_template, template_name, template_description, rule_name, rule_type, tag, description, condition_field, operator, expected_value, message, message_en, is_hard_rule, is_warning, priority, is_active, is_initial_enabled, is_renewal_enabled, created_at, updated_at, created_by, updated_by) FROM stdin;
\.


--
-- Data for Name: scholarship_sub_type_configs; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.scholarship_sub_type_configs (id, scholarship_type_id, sub_type_code, name, name_en, description, description_en, amount, currency, display_order, is_active, created_at, updated_at, created_by, updated_by) FROM stdin;
\.


--
-- Data for Name: school_identities; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.school_identities (id, name) FROM stdin;
\.


--
-- Data for Name: studying_statuses; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.studying_statuses (id, name) FROM stdin;
\.


--
-- Data for Name: system_settings; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.system_settings (id, key, value, category, data_type, is_sensitive, is_readonly, description, validation_regex, default_value, last_modified_by, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: user_profile_history; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.user_profile_history (id, user_id, field_name, old_value, new_value, change_reason, changed_at, ip_address, user_agent) FROM stdin;
\.


--
-- Data for Name: user_profiles; Type: TABLE DATA; Schema: public; Owner: scholarship_user
--

COPY public.user_profiles (id, user_id, bank_code, account_number, bank_document_photo_url, bank_document_object_name, advisor_name, advisor_email, advisor_nycu_id, preferred_language, custom_fields, privacy_settings, created_at, updated_at) FROM stdin;
\.


--
-- Name: academies_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.academies_id_seq', 1, false);


--
-- Name: admin_scholarships_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.admin_scholarships_id_seq', 1, false);


--
-- Name: application_documents_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.application_documents_id_seq', 1, false);


--
-- Name: application_fields_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.application_fields_id_seq', 1, false);


--
-- Name: application_files_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.application_files_id_seq', 1, false);


--
-- Name: application_reviews_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.application_reviews_id_seq', 1, false);


--
-- Name: applications_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.applications_id_seq', 3, true);


--
-- Name: audit_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.audit_logs_id_seq', 1, false);


--
-- Name: college_ranking_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.college_ranking_items_id_seq', 1, false);


--
-- Name: college_rankings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.college_rankings_id_seq', 1, false);


--
-- Name: college_reviews_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.college_reviews_id_seq', 1, false);


--
-- Name: configuration_audit_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.configuration_audit_logs_id_seq', 1, false);


--
-- Name: degrees_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.degrees_id_seq', 1, false);


--
-- Name: departments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.departments_id_seq', 1, false);


--
-- Name: email_history_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.email_history_id_seq', 1, false);


--
-- Name: email_templates_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.email_templates_id_seq', 1, false);


--
-- Name: identities_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.identities_id_seq', 1, false);


--
-- Name: notification_preferences_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.notification_preferences_id_seq', 1, false);


--
-- Name: notification_queue_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.notification_queue_id_seq', 1, false);


--
-- Name: notification_reads_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.notification_reads_id_seq', 1, false);


--
-- Name: notification_templates_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.notification_templates_id_seq', 1, false);


--
-- Name: notifications_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.notifications_id_seq', 1, false);


--
-- Name: payment_roster_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.payment_roster_items_id_seq', 6, true);


--
-- Name: payment_rosters_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.payment_rosters_id_seq', 5, true);


--
-- Name: professor_review_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.professor_review_items_id_seq', 1, false);


--
-- Name: professor_reviews_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.professor_reviews_id_seq', 1, false);


--
-- Name: professor_student_relationships_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.professor_student_relationships_id_seq', 2, true);


--
-- Name: quota_distributions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.quota_distributions_id_seq', 1, false);


--
-- Name: roster_audit_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.roster_audit_logs_id_seq', 13, true);


--
-- Name: roster_schedules_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.roster_schedules_id_seq', 1, false);


--
-- Name: scheduled_emails_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.scheduled_emails_id_seq', 1, false);


--
-- Name: scholarship_configurations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.scholarship_configurations_id_seq', 1, true);


--
-- Name: scholarship_rules_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.scholarship_rules_id_seq', 1, false);


--
-- Name: scholarship_sub_type_configs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.scholarship_sub_type_configs_id_seq', 1, false);


--
-- Name: scholarship_types_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.scholarship_types_id_seq', 4, true);


--
-- Name: school_identities_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.school_identities_id_seq', 1, false);


--
-- Name: studying_statuses_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.studying_statuses_id_seq', 1, false);


--
-- Name: system_settings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.system_settings_id_seq', 1, false);


--
-- Name: user_profile_history_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.user_profile_history_id_seq', 1, false);


--
-- Name: user_profiles_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.user_profiles_id_seq', 1, false);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: scholarship_user
--

SELECT pg_catalog.setval('public.users_id_seq', 20, true);


--
-- PostgreSQL database dump complete
--

