#!/bin/bash

python -c "from deployer.initialize import initialize_database; initialize_database()"
INIT_EXIT=$?

if [ $INIT_EXIT -ne 0 ]; then
    echo "Initialization failed (exit $INIT_EXIT) — container kept alive for inspection. Use 'docker exec -it initializer bash'."
    sleep infinity
    exit $INIT_EXIT
fi

cleanup() {
    python -c "from deployer.save import create_restore_point; create_restore_point()"
    exit 0
}

trap cleanup SIGTERM SIGINT

sleep infinity &
wait $!
