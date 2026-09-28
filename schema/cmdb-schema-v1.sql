-- Adopted CWM classes and associations, followed by application-specific tables.
CREATE TABLE IF NOT EXISTS ModelElement (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) COLLATE utf8mb4_bin NULL,
    namespace BIGINT UNSIGNED NULL,
    UNIQUE KEY ModelElement_id_namespace_uq (id, namespace)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS Namespace (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    CONSTRAINT Namespace_ModelElement_fk FOREIGN KEY (id) REFERENCES ModelElement (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS Package (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    CONSTRAINT Package_Namespace_fk FOREIGN KEY (id) REFERENCES Namespace (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `Schema` (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    CONSTRAINT Schema_Package_fk FOREIGN KEY (id) REFERENCES Package (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS TaggedValue (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    tag VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    value TEXT NOT NULL,
    modelElement BIGINT UNSIGNED NULL,
    UNIQUE KEY TaggedValue_modelElement_tag_uq (modelElement, tag),
    CONSTRAINT TaggedValue_ModelElement_fk FOREIGN KEY (modelElement) REFERENCES ModelElement (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Complete the parent reference after both tables exist. This is not a data migration.
ALTER TABLE ModelElement
    ADD FOREIGN KEY IF NOT EXISTS ModelElement_namespace_fk (namespace) REFERENCES Namespace (id);

CREATE TABLE IF NOT EXISTS Machine (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    ipAddress VARCHAR(45) NOT NULL,
    hostName VARCHAR(255) NULL,
    macAddress VARCHAR(17) NULL,
    site VARCHAR(255) NULL,
    createdOn TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updatedOn TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY Machine_ipAddress_uq (ipAddress),
    CONSTRAINT Machine_Namespace_fk FOREIGN KEY (id) REFERENCES Namespace (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS SoftwareSystem (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    type VARCHAR(255) NULL,
    subtype VARCHAR(255) NULL,
    supplier VARCHAR(255) NULL,
    version VARCHAR(255) NULL,
    CONSTRAINT SoftwareSystem_Package_fk FOREIGN KEY (id) REFERENCES Package (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS Component (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    CONSTRAINT Component_Namespace_fk FOREIGN KEY (id) REFERENCES Namespace (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS DeployedComponent (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    pathname TEXT NOT NULL,
    machine BIGINT UNSIGNED NOT NULL,
    component BIGINT UNSIGNED NOT NULL,
    CONSTRAINT DeployedComponent_Package_fk FOREIGN KEY (id) REFERENCES Package (id),
    -- The explicit machine reference must equal the inherited owner.
    CONSTRAINT DeployedComponent_owner_fk
        FOREIGN KEY (id, machine) REFERENCES ModelElement (id, namespace),
    CONSTRAINT DeployedComponent_machine_fk FOREIGN KEY (machine) REFERENCES Machine (id),
    CONSTRAINT DeployedComponent_component_fk FOREIGN KEY (component) REFERENCES Component (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS DataManager (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    CONSTRAINT DataManager_DeployedComponent_fk FOREIGN KEY (id) REFERENCES DeployedComponent (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- The CWM DataManagerDataPackage association preserves both many-valued ends.
CREATE TABLE IF NOT EXISTS DataManagerDataPackage (
    dataManager BIGINT UNSIGNED NOT NULL,
    dataPackage BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (dataManager, dataPackage),
    CONSTRAINT DataManagerDataPackage_manager_fk FOREIGN KEY (dataManager) REFERENCES DataManager (id),
    CONSTRAINT DataManagerDataPackage_package_fk FOREIGN KEY (dataPackage) REFERENCES Package (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Application policy referencing inventory, not a CWM class or subclass.
CREATE TABLE IF NOT EXISTS BackupSchedule (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    modelElement BIGINT UNSIGNED NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    frequency VARCHAR(16) COLLATE utf8mb4_bin NOT NULL DEFAULT 'daily',
    retention VARCHAR(16) COLLATE utf8mb4_bin NOT NULL DEFAULT '1-week',
    UNIQUE KEY BackupSchedule_modelElement_uq (modelElement),
    CONSTRAINT BackupSchedule_ModelElement_fk FOREIGN KEY (modelElement) REFERENCES ModelElement (id),
    CONSTRAINT BackupSchedule_enabled_ck CHECK (enabled IN (0, 1)),
    CONSTRAINT BackupSchedule_frequency_ck CHECK (frequency IN ('daily')),
    CONSTRAINT BackupSchedule_retention_ck CHECK (retention IN ('1-week', '2-weeks', '1-month', 'forever'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
