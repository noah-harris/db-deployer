# db-deployer

A containerized tool that spins up a fresh database, runs all your SQL scripts in the right order, and restores your data from the last known-good backup — all automatically, every time.

---

## What It Does

db-deployer solves the problem of standing up a database environment that's consistent, repeatable, and safe to tear down. Point it at a folder of SQL scripts and a backup directory, and it handles the rest:

- **Initializes** a fresh SQL Server or PostgreSQL database by running your SQL scripts in a defined order (schemas → tables → views → stored procedures → etc.)
- **Restores** table data from the most recent restore point, so every deployment starts with real data in the right state
- **Backs up** all table data to CSV files when the container shuts down, creating a new timestamped restore point automatically

The result is a database environment you can confidently destroy and recreate. Shut it down after a demo, a test run, or a development session — bring it back up and it's exactly where you left it.

---

## How It Works

The system runs as two Docker containers:

1. **The database** — a standard image for any supported database dialect. This is not part of this repo.
2. **The initializer** — the image built by this repo. A Python application that waits for the database to be ready, then does all the work.

When the initializer starts, it reads your SQL scripts from the mounted project directory and executes them in the order defined by `order.json`. Once the schema is in place, it scans the restore point directory, finds the most recent backup, and imports each table's CSV file into the database. The whole process is automatic and requires no manual intervention.

When the container receives a shutdown signal, the initializer exports every table to a fresh CSV in a new timestamped folder before stopping. This becomes the restore point for the next run.

Restore points are stored as plain CSV files, organized by timestamp (`YYYY-MM-DD HH.MM.SS`). They're human-readable, portable, and don't require any special tooling to inspect or archive.

---

## How to Use It

### Prerequisites

- Docker and Docker Compose installed
- A directory containing your SQL scripts (organized by database object type)
- A directory to store restore points (can start empty)

### 1. Configure Your Environment

Copy `.env.example` to `.env` and fill in the values:

```env
# "mssql" or "postgres"
DIALECT=mssql

# Database credentials
USERNAME=sa
PASSWORD=YourStrong!Passw0rd

# Port exposed on the host machine
EXTERNAL_PORT=1433

# Full paths to your SQL scripts and restore point directories
# Use SMB/CIFS paths (e.g. //server/share/path) for network shares,
# or absolute local paths for local directories.
SQL_PROJECT_DIRECTORY=//your-server/share/sql-scripts
RESTORE_POINT_DIRECTORY=//your-server/share/backups

# Credentials for mounting network shares (leave blank for local paths)
PRIMARY_SERVER_USERNAME=your-smb-username
PRIMARY_SERVER_PASSWORD=your-smb-password
```

### 2. Set Up Your SQL Project Directory

Your SQL project directory should be organized like this:

```
sql-scripts/
├── order.json              ← defines the creation order for all objects
└── your_database_name/
    ├── schema/
    │   └── dbo.sql
    ├── table/
    │   ├── dbo.Customers.sql
    │   └── dbo.Orders.sql
    ├── view/
    │   └── dbo.CustomerSummary.sql
    └── stored-procedure/
        └── dbo.GetOrder.sql
```

`order.json` tells the initializer what to create and in what order:

```json
[
  { "database": "your_database_name", "schema": "dbo", "type": "schema",   "name": "dbo" },
  { "database": "your_database_name", "schema": "dbo", "type": "table",    "name": "Customers" },
  { "database": "your_database_name", "schema": "dbo", "type": "table",    "name": "Orders" },
  { "database": "your_database_name", "schema": "dbo", "type": "view",     "name": "CustomerSummary" }
]
```

### 3. Set Up Your Restore Point Directory

The restore point directory can start empty — db-deployer will create the first backup when you shut down the container. After the first run, it will look like this:

```
backups/
└── 2025-05-09 14.30.00/
    └── your_database_name/
        ├── dbo.Customers.csv
        └── dbo.Orders.csv
```

On the next startup, db-deployer automatically finds the most recent timestamped folder and restores from it.

### 4. Start the Stack

```bash
docker compose up
```

To run in the background:

```bash
docker compose up -d
```

### 5. Shut Down (and Save a Restore Point)

```bash
docker compose down
```

This sends a shutdown signal to the initializer, which exports all table data before stopping. Your data is preserved for the next run.

---

## Mounting Directories

db-deployer uses Docker volumes to mount both directories into the container. The `docker-compose.yml` handles this automatically using the values from your `.env` file.

**For network shares (SMB/CIFS)**, the compose file mounts the paths using the CIFS driver with the credentials you provide. No manual mounting is required on the host.

**For local directories**, you can modify the volume definitions in `docker-compose.yml` to use bind mounts instead:

```yaml
volumes:
  sql-scripts:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /absolute/path/to/your/sql-scripts

  restore:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /absolute/path/to/your/backups
```

---

## Supported Databases

| Database          | Dialect value |
|-------------------|---------------|
| Microsoft SQL Server | `mssql`    |
| PostgreSQL        | `postgres`    |
