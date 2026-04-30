-- Schema MySQL alinhado com o runtime SQLite do Oraculo.

CREATE DATABASE IF NOT EXISTS `oraculo` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `oraculo`;

CREATE TABLE IF NOT EXISTS `ohlcv_1m` (
  `ts` BIGINT NOT NULL,
  `simbolo` VARCHAR(16) NOT NULL,
  `open` DOUBLE NULL,
  `high` DOUBLE NULL,
  `low` DOUBLE NULL,
  `close` DOUBLE NULL,
  `volume` DOUBLE NULL,
  PRIMARY KEY (`ts`, `simbolo`),
  KEY `idx_ohlcv_1m_simbolo_ts` (`simbolo`, `ts`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `livro_topo` (
  `ts` BIGINT NOT NULL,
  `simbolo` VARCHAR(16) NOT NULL,
  `bid_price` DOUBLE NULL,
  `bid_qty` DOUBLE NULL,
  `ask_price` DOUBLE NULL,
  `ask_qty` DOUBLE NULL,
  PRIMARY KEY (`ts`, `simbolo`),
  KEY `idx_livro_topo_simbolo_ts` (`simbolo`, `ts`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `features_1m` (
  `ts` BIGINT NOT NULL,
  `simbolo` VARCHAR(16) NOT NULL,
  `features_json` LONGTEXT NOT NULL,
  PRIMARY KEY (`ts`, `simbolo`),
  KEY `idx_features_1m_simbolo_ts` (`simbolo`, `ts`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `predictions` (
  `created_ts` BIGINT NOT NULL,
  `simbolo` VARCHAR(16) NOT NULL,
  `y_hat` DOUBLE NULL,
  `y_cal` DOUBLE NULL,
  `ic68_low` DOUBLE NULL,
  `ic68_high` DOUBLE NULL,
  `p_conf` DOUBLE NULL,
  `meta_json` LONGTEXT NULL,
  PRIMARY KEY (`created_ts`, `simbolo`),
  KEY `idx_predictions_simbolo_ts` (`simbolo`, `created_ts`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `outcomes` (
  `ts_previsao` BIGINT NOT NULL,
  `ts_target` BIGINT NOT NULL,
  `simbolo` VARCHAR(16) NOT NULL,
  `y_true` DOUBLE NULL,
  `y_hat` DOUBLE NULL,
  `err_rel` DOUBLE NULL,
  PRIMARY KEY (`ts_previsao`, `simbolo`),
  KEY `idx_outcomes_simbolo_ts` (`simbolo`, `ts_previsao`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `config` (
  `chave` VARCHAR(128) NOT NULL,
  `valor` LONGTEXT NULL,
  `tipo` VARCHAR(16) NOT NULL DEFAULT 'STRING',
  `atualizado_em` BIGINT NOT NULL,
  PRIMARY KEY (`chave`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `usuarios` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `nome` VARCHAR(128) NOT NULL,
  `api_key_ref` TEXT NULL,
  `api_secret_ref` TEXT NULL,
  `api_key_secret_id` VARCHAR(128) NULL,
  `api_secret_secret_id` VARCHAR(128) NULL,
  `ativo` TINYINT(1) NOT NULL DEFAULT 1,
  `testnet` TINYINT(1) NOT NULL DEFAULT 1,
  `risk_config_json` LONGTEXT NOT NULL,
  `criado_em` BIGINT NOT NULL,
  `atualizado_em` BIGINT NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_usuarios_nome` (`nome`),
  KEY `idx_usuarios_ativo_nome` (`ativo`, `nome`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `ordens` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `created_ts` BIGINT NOT NULL,
  `updated_ts` BIGINT NOT NULL,
  `usuario_id` BIGINT NULL,
  `simbolo` VARCHAR(16) NOT NULL,
  `lado` VARCHAR(8) NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `modo` VARCHAR(32) NOT NULL,
  `preco_referencia` DOUBLE NULL,
  `quantidade` DOUBLE NULL,
  `notional` DOUBLE NULL,
  `stop_loss_pct` DOUBLE NULL,
  `take_profit_pct` DOUBLE NULL,
  `detalhe_json` LONGTEXT NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_ordens_usuario_status_ts` (`usuario_id`, `status`, `created_ts`),
  KEY `idx_ordens_simbolo_ts` (`simbolo`, `created_ts`),
  CONSTRAINT `fk_ordens_usuario` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `audit` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `created_ts` BIGINT NOT NULL,
  `simbolo` VARCHAR(16) NOT NULL,
  `tipo` VARCHAR(64) NOT NULL,
  `payload_json` LONGTEXT NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_audit_simbolo_ts` (`simbolo`, `created_ts`),
  KEY `idx_audit_tipo_ts` (`tipo`, `created_ts`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `fila_sinais` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `created_ts` BIGINT NOT NULL,
  `updated_ts` BIGINT NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `tentativas` INT NOT NULL DEFAULT 0,
  `disponivel_em` BIGINT NOT NULL,
  `ordem_id` BIGINT NULL,
  `usuario_id` BIGINT NULL,
  `simbolo` VARCHAR(16) NOT NULL,
  `correlation_id` VARCHAR(128) NOT NULL,
  `payload_json` LONGTEXT NOT NULL,
  `erro_json` LONGTEXT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_fila_sinais_status_disponivel` (`status`, `disponivel_em`, `id`),
  KEY `idx_fila_sinais_correlation_id` (`correlation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
