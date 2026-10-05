-- 0.1.0 -> 0.2.0：保留旧表；活跃旧额度由限流器初始化时保守继承。
-- 升级前停止旧版写入。禁止在仍有配额债务时删除此表或回退到旧代码。
CREATE TABLE `captcha_rate_state` (
  `id` text PRIMARY KEY NOT NULL,
  `tat_us` integer DEFAULT 0 NOT NULL,
  `blocked_until_us` integer DEFAULT 0 NOT NULL
);
CREATE INDEX `rate_state_tat` ON `captcha_rate_state` (`tat_us`);
CREATE INDEX `rate_state_blocked` ON `captcha_rate_state` (`blocked_until_us`);
