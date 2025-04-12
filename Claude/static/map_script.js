document.addEventListener('DOMContentLoaded', () => {
    const mapContainer = document.getElementById('map-container');
    const robotElement = document.getElementById('robot');
    const targetCoordsSpan = document.getElementById('target-coords');
    const robotCoordsSpan = document.getElementById('robot-coords');
    const robotAngleSpan = document.getElementById('robot-angle');
    const navigateButton = document.getElementById('navigate-button');
    const clearButton = document.getElementById('clear-button');
    const resetStartButton = document.getElementById('reset-start-button');  // New button
    const updateCalibrationButton = document.getElementById('update-calibration-button');
    const goUpButton = document.getElementById('go-up-button');
    const turn90RightButton = document.getElementById('turn-90-right-button');
    const turn90LeftButton = document.getElementById('turn-90-left-button');

    // Obstacle mode controls
    let obstacleMode = false;
    const toggleObstaclesButton = document.getElementById('toggleObstaclesButton');
    const resetObstaclesButton = document.getElementById('resetObstaclesButton');
    const obstacleStatus = document.getElementById('obstacleStatus');

    toggleObstaclesButton.addEventListener('click', () => {
        obstacleMode = !obstacleMode;
        obstacleStatus.textContent = obstacleMode ? "On" : "Off";
        toggleObstaclesButton.textContent = obstacleMode ? "Exit Obstacle Mode" : "Toggle Obstacles Mode";
    });

    resetObstaclesButton.addEventListener('click', () => {
        const gridCells = document.querySelectorAll('.grid-cell');
        gridCells.forEach(cell => cell.classList.remove('obstacle'));
    });

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
    const updateTimingButton = document.getElementById("update-timing-button");

updateTimingButton.addEventListener("click", () => {
    const forwardDelayInput = document.getElementById("forward-delay-input").value;
    const turnLeftDelayInput = document.getElementById("turn-left-delay-input").value;
    const turnRightDelayInput = document.getElementById("turn-right-delay-input").value;
    const timingData = {
        forward_delay: parseFloat(forwardDelayInput),
        turn_left_delay: parseFloat(turnLeftDelayInput),
        turn_right_delay: parseFloat(turnRightDelayInput)
    };
    socket.emit("update_timing", timingData);
    console.log("Navigation timing update sent:", timingData);
});

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
        // Compute the center of the cell.
        const centerX = col * CELL_SIZE_PX + CELL_SIZE_PX / 2;
        const centerY = row * CELL_SIZE_PX + CELL_SIZE_PX / 2;
        
        // Position the robot element centered in the cell.
        robotElement.style.left = `${centerX}px`;
        robotElement.style.top = `${centerY}px`;
        
        // Use transform translate(-50%, -50%) to center the element,
        // then rotate. (Using 90 - angle here if that fits your telemetry direction.)
        const cssAngle = 90 - angle;
        robotElement.style.transform = `translate(-50%, -50%) rotate(${cssAngle}deg)`;
    
        // Update global state variables for display info.
        currentRobotPos = { row, col };
        currentRobotAngle = angle;
        updateInfoPanel();
    }

    // --- Cell Interaction ---
    function handleCellClick(event) {
        const clickedCell = event.target;
        
        // If obstacle mode is active, toggle the obstacle state instead of target selection.
        if (obstacleMode) {
            clickedCell.classList.toggle('obstacle');
            updateObstacles();  // <-- Emit updated obstacles list here

            return;
        }
        
        // Otherwise, proceed with target selection.
        const row = parseInt(clickedCell.dataset.row);
        const col = parseInt(clickedCell.dataset.col);
    
        if (clickedCell === currentSelectedCell) {
            // Deselecting the target.
            clickedCell.classList.remove('selected');
            currentSelectedCell = null;
            currentTarget = null;
            if (socket) {
                console.log('Target cleared by re-click, sending clear command');
                socket.emit('clear_target');
            }
        } else {
            // Selecting a new target.
            if (currentSelectedCell) {
                currentSelectedCell.classList.remove('selected');
            }
            clickedCell.classList.add('selected');
            currentSelectedCell = clickedCell;
            currentTarget = { row, col };
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
        // Display the robot's position as (row, col) to match the target format.
        robotCoordsSpan.textContent = `(${currentRobotPos.row.toFixed(1)}, ${currentRobotPos.col.toFixed(1)})`;
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
        if (socket) {
            console.log('Sending clear target command via button');
            socket.emit('clear_target');
        }
    });
    
    resetStartButton.addEventListener('click', () => {
        console.log("Requesting reset of start position");
        if (socket) {
            socket.emit('reset_start');
        } else {
            alert("WebSocket is not connected!");
        }
    });
    
    navigateButton.addEventListener('click', () => {
        if (currentTarget && socket) {
            console.log(`Sending navigation request to: Row ${currentTarget.row}, Col ${currentTarget.col}`);
            socket.emit('navigate_to', { row: currentTarget.row, col: currentTarget.col });
        } else {
            console.error(`Cannot navigate: ${!currentTarget ? 'No target selected.' : 'WebSocket not ready.'}`);
            alert(`Cannot navigate: ${!currentTarget ? 'No target selected.' : 'WebSocket not ready.'}`);
        }
    });
    
    goUpButton.addEventListener('click', () => {
        console.log("Requesting to go up 1 unit");
        if (socket) {
            socket.emit('go_up');
        } else {
            alert("WebSocket is not connected!");
        }
    });
    
    turn90RightButton.addEventListener('click', () => {
        console.log("Requesting turn 90° right");
        if (socket) {
            socket.emit('turn_90_right');
        } else {
            alert("WebSocket is not connected!");
        }
    });
turn90LeftButton.addEventListener('click', () => {
    console.log("Requesting turn 90° Left");
    if (socket) {
        socket.emit('turn_90_left'); // Use exactly the same event name as on the server
    } else {
        alert("WebSocket is not connected!");
    }
});

   
    
    // --- WebSocket Setup ---
    function updateObstacles() {
    const gridCells = document.querySelectorAll('.grid-cell');
    const obstacles = [];
    gridCells.forEach(cell => {
        if (cell.classList.contains('obstacle')) {
        const r = parseInt(cell.dataset.row);
        const c = parseInt(cell.dataset.col);
        obstacles.push([r, c]);
        }
    });
    socket.emit('update_obstacles', obstacles);
    console.log("Obstacles sent:", obstacles);
    }

    function setupWebSocket() {
        try {
            const sock = io({
                reconnectionAttempts: 5,
                timeout: 10000
            });
    
            sock.on('connect', () => {
                console.log(`Connected to WebSocket server with ID: ${sock.id}`);
            });
    
            sock.on('disconnect', (reason) => {
                console.log(`Disconnected from WebSocket server: ${reason}`);
            });
    
            sock.on('connect_error', (error) => {
                console.error('WebSocket connection error:', error);
            });
    
            // Listen for robot pose updates
            sock.on('robot_update', (data) => {
                if (data.row !== undefined && data.col !== undefined && data.angle !== undefined) {
                    updateRobotVisuals(data.row, data.col, data.angle);
                } else {
                    console.warn("Received incomplete robot update data:", data);
                }
            });
    
            sock.on('log', (logData) => {
                if (logData && logData.msg) {
                    console.log(`[Server Log] ${logData.msg}`);
                } else {
                    console.log(`[Server Log] ${logData}`);
                }
            });
    
            return sock;
        } catch (e) {
            console.error("Failed to initialize WebSocket:", e);
            alert("Error connecting to WebSocket server. Please check console.");
            return null;
        }
    }
    
    // --- Initial Setup ---
    initMap();
    socket = setupWebSocket();
});
