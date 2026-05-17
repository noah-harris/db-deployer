import dotenv
dotenv.load_dotenv("Z:\\Repositories\\db-deployer\\.env")  # Load environment variables from .env file
import dialects
import config
config.SQL_SCRIPTS_DIR = "Z:/Repositories/ledgr/database"  # Override SQL_SCRIPTS_DIR for testing

logger = config.make_logger("test.entrypoint")
dialect: dialects.SqlDialect = dialects.mapping.get(config.DIALECT.lower())

order = dialect._get_project_load_order()
for obj in order:
    print(obj, obj.dependencies)