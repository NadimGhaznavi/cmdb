-- Only the adopted CWM classes, with exact class names and attribute casing.
CREATE TABLE IF NOT EXISTS ModelElement (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    namespace BIGINT UNSIGNED NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS Namespace (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    CONSTRAINT Namespace_ModelElement_fk FOREIGN KEY (id) REFERENCES ModelElement (id)
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
    CONSTRAINT SoftwareSystem_Namespace_fk FOREIGN KEY (id) REFERENCES Namespace (id)
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
    CONSTRAINT DeployedComponent_Namespace_fk FOREIGN KEY (id) REFERENCES Namespace (id),
    CONSTRAINT DeployedComponent_machine_fk FOREIGN KEY (machine) REFERENCES Machine (id),
    CONSTRAINT DeployedComponent_component_fk FOREIGN KEY (component) REFERENCES Component (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
