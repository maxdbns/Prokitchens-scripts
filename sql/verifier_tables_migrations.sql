SELECT
    table_name,
    CASE WHEN table_name IN (
        'profiles', 'territories', 'activity_log', 'tasks', 'webhook_subscriptions',
        'duplicate_groups', 'lead_changes', 'tender_notices', 'tender_notice_locations',
        'tender_notice_alerts', 'tender_notice_leads', 'pipeline_stats', 'tags', 'lead_tags'
    ) THEN 'migration post-2026-07-09' ELSE 'autre' END as source
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY source, table_name;
