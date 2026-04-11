"""
keyboard_tester.py — Keyboard layout testing and calibration utility.

Runs a simple test to help users identify their keyboard layout
and configure custom character-to-OEM mappings.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger("utils.keyboard_tester")

# Path to store custom keyboard mappings
CONFIG_DIR = Path.home() / ".macro_deck"
KEYBOARD_CONFIG_FILE = CONFIG_DIR / "keyboard_config.json"


def get_keyboard_config() -> dict:
    """Load custom keyboard configuration if it exists."""
    if KEYBOARD_CONFIG_FILE.exists():
        try:
            with open(KEYBOARD_CONFIG_FILE) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load keyboard config: {e}")
    return {}


def save_keyboard_config(config: dict) -> bool:
    """Save custom keyboard configuration."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(KEYBOARD_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info(f"Saved keyboard config to {KEYBOARD_CONFIG_FILE}")
        return True
    except Exception as e:
        logger.error(f"Failed to save keyboard config: {e}")
        return False


def create_keyboard_test_html() -> str:
    """Create an HTML page for testing keyboard layout."""
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>MacroDeck - Keyboard Layout Tester</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .container { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1 { color: #333; }
        .info-box { background: #e8f4f8; border-left: 4px solid #2196F3; padding: 15px; margin: 15px 0; }
        .keyboard-test {
            display: grid;
            grid-template-columns: repeat(10, 1fr);
            gap: 8px;
            margin: 20px 0;
        }
        .key-button {
            padding: 15px;
            background: #f0f0f0;
            border: 2px solid #ddd;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            text-align: center;
            transition: all 0.2s;
        }
        .key-button:hover { background: #e0e0e0; border-color: #999; }
        .key-button.active { background: #4CAF50; color: white; border-color: #2e7d32; }
        .key-button.error { background: #f44336; color: white; border-color: #c62828; }
        .result {
            margin: 20px 0;
            padding: 15px;
            background: #f9f9f9;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .layout-display {
            background: white;
            border: 2px solid #2196F3;
            padding: 15px;
            margin: 15px 0;
            border-radius: 4px;
        }
        .char-mapping {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            margin: 10px 0;
        }
        .char-item {
            padding: 10px;
            background: #f0f0f0;
            border-radius: 4px;
            border: 1px solid #ddd;
        }
        .char-item strong { color: #2196F3; }
        button {
            background: #2196F3;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }
        button:hover { background: #1976D2; }
        .error-message { color: #f44336; margin: 10px 0; }
        .success-message { color: #4CAF50; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⌨️ Keyboard Layout Tester</h1>
        
        <div class="info-box">
            <strong>What is this?</strong><br>
            This tool helps identify your keyboard layout and map special characters correctly.
            If Type Text doesn't record characters like /, ., or : correctly, use this tool to configure your layout.
        </div>

        <h2>Current Layout Detection</h2>
        <div id="layoutInfo" class="layout-display">
            <p>Detecting keyboard layout...</p>
        </div>

        <h2>Test Individual Keys</h2>
        <p>Press the buttons below to test what each OEM key produces on your keyboard:</p>
        
        <div class="keyboard-test" id="keyboardTest"></div>

        <h2>Test Complete Strings</h2>
        <input type="text" id="testString" placeholder="Type or paste text to test" size="60" style="padding: 10px;">
        <button onclick="analyzeString()">Analyze</button>
        
        <div id="result" class="result" style="display:none;"></div>
    </div>

    <script>
        // Fetch and display keyboard layout info
        async function loadLayoutInfo() {
            try {
                const response = await fetch('/api/keyboard/layout');
                const data = await response.json();
                displayLayoutInfo(data);
            } catch (error) {
                document.getElementById('layoutInfo').innerHTML = 
                    '<p class="error-message">Error detecting layout: ' + error.message + '</p>';
            }
        }

        function displayLayoutInfo(data) {
            const layout = data.layout || 'UNKNOWN';
            const mappings = data.mappings || {};
            
            let html = `<h3>Detected Layout: <strong>${layout}</strong></h3>`;
            html += '<p><strong>OEM Key Mappings for your layout:</strong></p>';
            html += '<div class="char-mapping">';
            
            Object.entries(mappings).forEach(([key, char]) => {
                if (char) {
                    html += `<div class="char-item"><strong>${key}</strong>: <code>"${char}"</code></div>`;
                }
            });
            
            html += '</div>';
            
            document.getElementById('layoutInfo').innerHTML = html;
        }

        function createKeyboardTest() {
            const keys = [
                'oem_1', 'oem_2', 'oem_3', 'oem_4', 'oem_5',
                'oem_6', 'oem_7', 'oem_comma', 'oem_period', 'oem_plus',
                'oem_minus'
            ];
            
            const container = document.getElementById('keyboardTest');
            keys.forEach(key => {
                const btn = document.createElement('button');
                btn.className = 'key-button';
                btn.textContent = key;
                btn.onclick = () => testKey(key, btn);
                container.appendChild(btn);
            });
        }

        async function testKey(keyName, button) {
            try {
                // This would require a backend endpoint to press the key
                // For now, we'll just show what the mapping says
                const response = await fetch('/api/keyboard/layout');
                const data = await response.json();
                const char = data.mappings?.[keyName];
                
                button.classList.add('active');
                setTimeout(() => button.classList.remove('active'), 300);
                
                if (char) {
                    showResult(`<strong>${keyName}</strong> produces: <code>&quot;${char}&quot;</code>`);
                } else {
                    showResult(`<strong>${keyName}</strong> has no mapping for your layout`);
                }
            } catch (error) {
                button.classList.add('error');
                showResult(`<span class="error-message">Error: ${error.message}</span>`);
            }
        }

        function analyzeString() {
            const str = document.getElementById('testString').value;
            if (!str) {
                showResult('<span class="error-message">Please enter text to analyze</span>');
                return;
            }
            
            // This is a client-side analysis showing what each character would produce
            let analysis = '<h3>Character Analysis</h3>';
            analysis += '<table style="width:100%; border-collapse: collapse;">';
            analysis += '<tr style="border-bottom: 1px solid #ddd;"><th style="text-align:left;">Char</th><th style="text-align:left;">Code</th><th style="text-align:left;">Info</th></tr>';
            
            for (let char of str) {
                const code = char.charCodeAt(0);
                const info = getCharInfo(char);
                analysis += `<tr style="border-bottom: 1px solid #ddd;">
                    <td><code>"${char}"</code></td>
                    <td>U+${code.toString(16).toUpperCase().padStart(4, '0')}</td>
                    <td>${info}</td>
                </tr>`;
            }
            analysis += '</table>';
            showResult(analysis);
        }

        function getCharInfo(char) {
            const problematicChars = {
                '/': 'Forward slash - may need special mapping',
                '.': 'Period - may need special mapping',
                ':': 'Colon - may need special mapping',
                ';': 'Semicolon - may need special mapping',
                '£': 'Pound sign - common AZERTY issue',
                '§': 'Section sign - common AZERTY issue',
            };
            return problematicChars[char] || 'Standard character';
        }

        function showResult(html) {
            const resultDiv = document.getElementById('result');
            resultDiv.innerHTML = html;
            resultDiv.style.display = 'block';
        }

        // Initialize on page load
        window.onload = () => {
            loadLayoutInfo();
            createKeyboardTest();
        };
    </script>
</body>
</html>
"""
