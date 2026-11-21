-- Stop all Worker writers before applying this migration. A failed guard can
-- be retried after the last IP debt and fixed-window cooldown have expired.
CREATE TABLE IF NOT EXISTS captcha_ip_cutover_guard (
    active INTEGER CONSTRAINT wait_for_ip_quota_to_drain CHECK (active = 0)
);
INSERT INTO captcha_ip_cutover_guard (active)
SELECT EXISTS (
    SELECT 1 FROM captcha_rate_state
    WHERE substr(id, 1, instr(id, ':') - 1) IN ('init', 'ip', 'verify-ip', 'submit-ip')
      AND (tat_us > unixepoch() * 1000000 OR blocked_until_us > unixepoch() * 1000000)
) OR EXISTS (
    SELECT 1 FROM captcha_rates
    WHERE substr(id, 1, instr(id, ':') - 1) IN ('init', 'ip', 'verify-ip', 'submit-ip')
      AND expires > unixepoch() * 1000
);

DELETE FROM captcha_rate_state
WHERE substr(id, 1, instr(id, ':') - 1) IN ('init', 'ip', 'verify-ip', 'submit-ip');
DELETE FROM captcha_rates
WHERE substr(id, 1, instr(id, ':') - 1) IN ('init', 'ip', 'verify-ip', 'submit-ip');
-- The two Worker versions must not be able to claim different IP buckets on
-- the same schema. Renaming also preserves session debt and its indexes.
ALTER TABLE captcha_rate_state RENAME TO captcha_quota_state;
DROP TABLE captcha_ip_cutover_guard;
