CREATE TABLE `captcha_challenges` (
	`id` text PRIMARY KEY NOT NULL,
	`session` text NOT NULL,
	`purpose` text NOT NULL,
	`answer` integer NOT NULL,
	`expires` integer NOT NULL,
	`attempts` integer DEFAULT 0 NOT NULL,
	`solved` integer DEFAULT 0 NOT NULL,
	`token` text,
	`token_expires` integer,
	`used` integer DEFAULT 0 NOT NULL
);
--> statement-breakpoint
CREATE INDEX `challenges_expiry` ON `captcha_challenges` (`expires`);--> statement-breakpoint
CREATE INDEX `challenges_token` ON `captcha_challenges` (`token`);--> statement-breakpoint
CREATE TABLE `captcha_rates` (
	`id` text PRIMARY KEY NOT NULL,
	`count` integer NOT NULL,
	`expires` integer NOT NULL
);
--> statement-breakpoint
CREATE INDEX `rates_expiry` ON `captcha_rates` (`expires`);--> statement-breakpoint
CREATE TABLE `captcha_sessions` (
	`id` text PRIMARY KEY NOT NULL,
	`csrf` text NOT NULL,
	`expires` integer NOT NULL
);
--> statement-breakpoint
CREATE INDEX `sessions_expiry` ON `captcha_sessions` (`expires`);