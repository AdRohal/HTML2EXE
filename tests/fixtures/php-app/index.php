<?php
// Minimal PHP fixture: proves PHP runs, sessions/files are writable, extensions load.
$data = sys_get_temp_dir();
echo "php-ok " . PHP_VERSION . " sqlite=" . (extension_loaded('pdo_sqlite') ? 'yes' : 'no')
   . " mbstring=" . (extension_loaded('mbstring') ? 'yes' : 'no')
   . " route=" . htmlspecialchars($_SERVER['REQUEST_URI']);
