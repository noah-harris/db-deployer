#!/bin/bash

python -c "from deployer.initialize import initialize_database; initialize_database()"
INIT_EXIT=$?

if [ $INIT_EXIT -ne 0 ]; then
    echo "Initialization failed (exit $INIT_EXIT) — container kept alive for inspection. Use 'docker exec -it initializer bash'."
    sleep infinity
    exit $INIT_EXIT
fi

python -c "from deployer.save import create_restore_point; create_restore_point()"
SAVE_EXIT=$?

if [ $SAVE_EXIT -ne 0 ]; then
    echo "Restore point creation failed (exit $SAVE_EXIT) — container kept alive for inspection. Use 'docker exec -it initializer bash'."
    sleep infinity
    exit $SAVE_EXIT
fi

sleep infinity
