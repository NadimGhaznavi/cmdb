CREATE TABLE IF NOT EXISTS machines (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    ipAddress VARCHAR(45) NOT NULL,
    hostName VARCHAR(255) NULL,
    macAddress VARCHAR(17) NULL,
    site VARCHAR(255) NULL,
    createdOn TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updatedOn TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY machines_ipAddress_uq (ipAddress)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS softwareSystems (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    type VARCHAR(255) NULL,
    subtype VARCHAR(255) NULL,
    supplier VARCHAR(255) NULL,
    version VARCHAR(255) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS components (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS deployedSoftwareSystems (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    softwareSystem BIGINT UNSIGNED NOT NULL,
    CONSTRAINT deployedSoftwareSystems_softwareSystem_fk
        FOREIGN KEY (softwareSystem) REFERENCES softwareSystems (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS deployedComponents (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    pathname TEXT NOT NULL,
    machine BIGINT UNSIGNED NOT NULL,
    component BIGINT UNSIGNED NOT NULL,
    CONSTRAINT deployedComponents_machine_fk
        FOREIGN KEY (machine) REFERENCES machines (id),
    CONSTRAINT deployedComponents_component_fk
        FOREIGN KEY (component) REFERENCES components (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- CWM DeployedSoftwareSystemComponents has zero-to-many multiplicity at both ends.
CREATE TABLE IF NOT EXISTS deployedSoftwareSystemComponents (
    deployedSoftwareSystem BIGINT UNSIGNED NOT NULL,
    deployedComponent BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (deployedSoftwareSystem, deployedComponent),
    CONSTRAINT deployedSoftwareSystemComponents_system_fk
        FOREIGN KEY (deployedSoftwareSystem) REFERENCES deployedSoftwareSystems (id),
    CONSTRAINT deployedSoftwareSystemComponents_component_fk
        FOREIGN KEY (deployedComponent) REFERENCES deployedComponents (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
