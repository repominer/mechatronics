document.addEventListener('DOMContentLoaded', () => {
    const btnForward = document.getElementById('calib-forward');
    const btnBackward = document.getElementById('calib-backward');
    const btnLeft = document.getElementById('calib-left');
    const btnRight = document.getElementById('calib-right');
    const inputDistance = document.getElementById('measured-distance');
    const inputAngle = document.getElementById('measured-angle');
    const btnApply = document.getElementById('apply-calibration');
    const displayMoveDist = document.getElementById('current-move-distance');
    const displayTurnAngle = document.getElementById('current-turn-angle');
    const logArea = document.getElementById('calibration-log');

    let socket = null;

    function addLog(message) {
        logArea.innerHTML += `${new Date().toLocaleTimeString()}: ${message}<br>`;
        // Optional: Auto-scroll
        logArea.scrollTop = logArea.scrollHeight;
    }

    function setupWebSocket() {
        try {
            socket = io({ reconnectionAttempts: 5, timeout: 10000 });

            socket.on('connect', () => {
                addLog('Connected to WebSocket server.');
                // Request current values when connected
                socket.emit('request_calibration_values');
            });

            socket.on('disconnect', (reason) => {
                addLog(`Disconnected: ${reason}`);
            });

            socket.on('connect_error', (error) => {
                addLog(`Connection Error: ${error}`);
                console.error('WebSocket connection error:', error);
            });

            // Listen for current calibration values from server
            socket.on('calibration_values', (data) => {
                addLog('Received current calibration values.');
                if (data.move_distance !== undefined) {
                    displayMoveDist.textContent = data.move_distance.toFixed(3);
                }
                 if (data.turn_angle !== undefined) {
                    displayTurnAngle.textContent = data.turn_angle.toFixed(1);
                }
            });

            // Listen for log/feedback messages from calibration actions
            socket.on('calibration_log', (data) => {
                if (data && data.msg) {
                     addLog(`[Server] ${data.msg}`);
                } else {
                     addLog(`[Server] ${data}`);
                }
            });

        } catch (e) {
            addLog(`ERROR: Failed to initialize WebSocket - ${e}`);
            console.error("Failed to initialize WebSocket:", e);
        }
    }

    // --- Event Listeners ---

    btnForward.addEventListener('click', () => {
        if (socket) {
            addLog('Sending single Forward pulse command...');
            socket.emit('calibrate_command', { command: 'F' });
        } else { addLog('ERROR: Not connected.'); }
    });

    btnBackward.addEventListener('click', () => {
        if (socket) {
            addLog('Sending single Backward pulse command...');
            socket.emit('calibrate_command', { command: 'B' });
        } else { addLog('ERROR: Not connected.'); }
    });

    btnLeft.addEventListener('click', () => {
        if (socket) {
            addLog('Sending single Left pulse command...');
            socket.emit('calibrate_command', { command: 'L' });
        } else { addLog('ERROR: Not connected.'); }
    });

    btnRight.addEventListener('click', () => {
        if (socket) {
            addLog('Sending single Right pulse command...');
            socket.emit('calibrate_command', { command: 'R' });
        } else { addLog('ERROR: Not connected.'); }
    });

    btnApply.addEventListener('click', () => {
        const distValue = inputDistance.value;
        const angleValue = inputAngle.value;

        const calibrationData = {};
        let validData = false;

        if (distValue !== "" && !isNaN(parseFloat(distValue))) {
            calibrationData.distance = parseFloat(distValue);
            validData = true;
             addLog(`Applying distance: ${calibrationData.distance}`);
        } else if (distValue !== "") {
             addLog(`ERROR: Invalid distance value entered: ${distValue}`);
        }


        if (angleValue !== "" && !isNaN(parseFloat(angleValue))) {
            calibrationData.angle = parseFloat(angleValue);
            validData = true;
            addLog(`Applying angle: ${calibrationData.angle}`);
        } else if (angleValue !== "") {
            addLog(`ERROR: Invalid angle value entered: ${angleValue}`);
        }


        if (socket && validData) {
            socket.emit('apply_calibration', calibrationData);
            // Request updated values after applying
            setTimeout(() => socket.emit('request_calibration_values'), 500); // Delay slightly
        } else if (!socket) {
             addLog('ERROR: Not connected.');
        } else {
             addLog('No valid values entered to apply.');
        }
    });

    // --- Initial Setup ---
    addLog("Initializing calibration page...");
    setupWebSocket();

}); // End DOMContentLoaded