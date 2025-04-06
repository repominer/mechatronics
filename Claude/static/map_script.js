document.addEventListener('DOMContentLoaded', () => {
    const mapContainer = document.getElementById('map-container');
    const robotElement = document.getElementById('robot');
    const targetCoordsSpan = document.getElementById('target-coords');
    const robotCoordsSpan = document.getElementById('robot-coords');
    const robotAngleSpan = document.getElementById('robot-angle');
    const navigateButton = document.getElementById('navigate-button');
    const clearButton = document.getElementById('clear-button');

    // --- Configuration ---
    const GRID_SIZE = 20; // Match Python RobotMap grid_size if possible
    const CELL_SIZE_PX = 30; // Visual size of cells in pixels

    // --- State ---
    let currentRobotPos = { row: Math.floor(GRID_SIZE / 2), col: Math.floor(GRID_SIZE / 2) };
    let currentRobotAngle = 90; // Initial angle (90 = up, matches Python)
    let currentSelectedCell = null; // Reference to the selected cell element
    let currentTarget = null; // { row: r, col: c }
    let socket = null; // To hold the socket instance

    // --- Initialization ---
    function initMap() {
        document.documentElement.style.setProperty('--grid-size', GRID_SIZE);
        document.documentElement.style.setProperty('--cell-size', `${CELL_SIZE_PX}px`);
        mapContainer.innerHTML = '';
        mapContainer.appendChild(robotElement);
        for (let r = 0; r < GRID_SIZE; r++) {
            for (let c = 0; c < GRID_SIZE; c++) {
                const cell = document.createElement('div');
                cell.classList.add('grid-cell');
                cell.dataset.row = r;
                cell.dataset.col = c;
                cell.addEventListener('click', handleCellClick);
                mapContainer.appendChild(cell);
            }
        }
        updateRobotVisuals(currentRobotPos.row, currentRobotPos.col, currentRobotAngle);
        updateInfoPanel();
    }

    // --- Robot Visuals ---
    function updateRobotVisuals(row, col, angle) {
        const cellTop = row * CELL_SIZE_PX;
        const cellLeft = col * CELL_SIZE_PX;
        const robotTopOffset = CELL_SIZE_PX * 0.2;
        const robotLeftOffset = CELL_SIZE_PX * 0.5;
        robotElement.style.top = `${cellTop + robotTopOffset}px`;
        robotElement.style.left = `${cellLeft + robotLeftOffset}px`;
        const cssAngle = angle - 90;
        robotElement.style.transform = `translateX(-50%) rotate(${cssAngle}deg)`;
        // Update state (use precise values from backend if available)
        currentRobotPos = { row: row, col: col };
        currentRobotAngle = angle;
        updateInfoPanel(); // Update display text
    }

    // --- Cell Interaction ---
    function handleCellClick(event) {
        const clickedCell = event.target;
        const row = parseInt(clickedCell.dataset.row);
        const col = parseInt(clickedCell.dataset.col);

        if (clickedCell === currentSelectedCell) {
            // Deselecting
            clickedCell.classList.remove('selected');
            currentSelectedCell = null;
            currentTarget = null;
            if (socket) { // Also inform backend if target is cleared by re-clicking
                console.log('Target cleared by re-click, sending clear command');
                socket.emit('clear_target'); // SEND CLEAR
            }
        } else {
            // Selecting a new target
            if (currentSelectedCell) {
                currentSelectedCell.classList.remove('selected');
            }
            clickedCell.classList.add('selected');
            currentSelectedCell = clickedCell;
            currentTarget = { row, col };
             // Note: We don't emit 'navigate_to' on just a click, only on button press
             console.log(`Target selected: Row ${row}, Col ${col}`);
        }
        updateInfoPanel();
        updateNavigateButtonState();
    }

    // --- Info Panel & Button Updates ---
    function updateInfoPanel() {
        if (currentTarget) {
            targetCoordsSpan.textContent = `(${currentTarget.row}, ${currentTarget.col})`;
        } else {
            targetCoordsSpan.textContent = 'None';
        }
        // Display potentially fractional coordinates received from backend
        robotCoordsSpan.textContent = `(${currentRobotPos.col.toFixed(1)}, ${currentRobotPos.row.toFixed(1)})`; // Note: col is x, row is y
        robotAngleSpan.textContent = `${currentRobotAngle.toFixed(1)}`;
    }

    function updateNavigateButtonState() {
        navigateButton.disabled = !currentTarget;
    }

    // --- Button Actions ---
    clearButton.addEventListener('click', () => {
        if (currentSelectedCell) {
            currentSelectedCell.classList.remove('selected');
        }
        currentSelectedCell = null;
        currentTarget = null;
        updateInfoPanel();
        updateNavigateButtonState();
        if (socket) { // Check if socket exists
            console.log('Sending clear target command via button');
            socket.emit('clear_target'); // SEND CLEAR
        }
    });

    navigateButton.addEventListener('click', () => {
        if (currentTarget && socket) { // Check if socket exists and target selected
            console.log(`Sending navigation request to: Row ${currentTarget.row}, Col ${currentTarget.col}`);
            socket.emit('navigate_to', { row: currentTarget.row, col: currentTarget.col }); // SEND TARGET
            // Optional: Clear target visually after sending command? Depends on desired UX.
            // clearButton.click();
        } else {
            console.error(`Cannot navigate: ${!currentTarget ? 'No target selected.' : 'WebSocket not ready.'}`);
            alert(`Cannot navigate: ${!currentTarget ? 'No target selected.' : 'WebSocket not ready.'}`);
        }
    });

    // --- WebSocket Setup ---
    function setupWebSocket() {
        try {
             // Ensure Socket.IO library is included in map.html
            const sock = io({
                reconnectionAttempts: 5, // Example: Limit reconnection attempts
                timeout: 10000 // Example: Connection timeout
            });

            sock.on('connect', () => {
                console.log(`Connected to WebSocket server with ID: ${sock.id}`);
                // Potentially request initial state or confirm connection
            });

            sock.on('disconnect', (reason) => {
                console.log(`Disconnected from WebSocket server: ${reason}`);
            });

            sock.on('connect_error', (error) => {
                console.error('WebSocket connection error:', error);
            });

            // Listen for robot pose updates (Phase 1)
            sock.on('robot_update', (data) => {
                if (data.row !== undefined && data.col !== undefined && data.angle !== undefined) {
                    updateRobotVisuals(data.row, data.col, data.angle);
                } else {
                    console.warn("Received incomplete robot update data:", data);
                }
            });

             // Listen for log messages from server (optional but helpful)
            sock.on('log', (logData) => {
                if (logData && logData.msg) {
                     console.log(`[Server Log] ${logData.msg}`);
                } else {
                     console.log(`[Server Log] ${logData}`); // Handle plain string logs too
                }
            });

            return sock; // Return the socket instance

        } catch (e) {
            console.error("Failed to initialize WebSocket:", e);
            alert("Error connecting to WebSocket server. Please check console.");
            return null; // Indicate failure
        }
    }

    // --- Initial Setup ---
    initMap();
    socket = setupWebSocket(); // Assign the returned socket instance

}); // End DOMContentLoaded