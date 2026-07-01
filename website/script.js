document.addEventListener('DOMContentLoaded', () => {
    // The exact 20 free keys generated for the early adopters
    const masterKeys = [
        "0AG5-3FM1-Y2MX-ZD27",
        "1E9U-U4B7-B8W6-QKKD",
        "1RAJ-1NY5-9FW0-UQJ0",
        "2XMH-8DTD-4OSQ-AEMM",
        "3ITA-XCZX-7TW5-FKLF",
        "4UTT-B2FI-9ELP-1HMN",
        "5M4I-63LC-MH6M-STWP",
        "5UUT-MN5S-TZNX-D0ZH",
        "672T-9L6P-TE9Q-G0GK",
        "6WLF-5WZ9-0ER5-NOTH",
        "A4EE-8AT1-EE7U-B27F",
        "CXZ6-ZBM4-GC24-S9BN",
        "D0P7-933C-MH0S-3N6U",
        "DEJJ-YN1C-5L2R-Q31N",
        "ENUF-S15P-YBD6-XGCK",
        "F1XY-CFV1-5S30-4DFR",
        "F2WL-ZZPI-Y93A-J3OU",
        "FDHK-SMJ3-XEM9-KZCZ",
        "GSHU-R938-6ORE-804C",
        "HJ27-UP69-QE58-N3I7"
    ];

    const generateBtn = document.getElementById('generate-btn');
    const keyDisplayBox = document.getElementById('key-display');
    const theKeyText = document.getElementById('the-key');
    const copyBtn = document.getElementById('copy-btn');
    const exhaustedMsg = document.getElementById('exhausted-msg');
    const giveawayContainer = document.getElementById('giveaway-container');
    const keysCounter = document.getElementById('keys-counter');

    // Initialize local storage tracker if it doesn't exist
    if (!localStorage.getItem('indra_keys_given')) {
        localStorage.setItem('indra_keys_given', '0');
    }

    function updateUI() {
        const givenCount = parseInt(localStorage.getItem('indra_keys_given'));
        const remaining = masterKeys.length - givenCount;
        
        keysCounter.textContent = `${remaining} Keys Remaining`;

        if (remaining <= 0) {
            giveawayContainer.classList.add('hidden');
            exhaustedMsg.classList.remove('hidden');
        }
    }

    generateBtn.addEventListener('click', () => {
        let givenCount = parseInt(localStorage.getItem('indra_keys_given'));
        
        if (givenCount < masterKeys.length) {
            // Get the next key in the array
            const newKey = masterKeys[givenCount];
            
            // Display it
            theKeyText.textContent = newKey;
            keyDisplayBox.classList.remove('hidden');
            
            // Increment tracker and save
            givenCount++;
            localStorage.setItem('indra_keys_given', givenCount.toString());
            
            // Update counter
            updateUI();
            
            // Small visual effect
            generateBtn.textContent = "Key Generated!";
            generateBtn.style.background = "#4ade80"; // Green
            setTimeout(() => {
                generateBtn.textContent = "Generate Free Key";
                generateBtn.style.background = "";
            }, 2000);
        }
    });

    copyBtn.addEventListener('click', () => {
        const text = theKeyText.textContent;
        navigator.clipboard.writeText(text).then(() => {
            const originalText = copyBtn.textContent;
            copyBtn.textContent = "Copied!";
            copyBtn.style.background = "#fff";
            copyBtn.style.color = "#000";
            setTimeout(() => {
                copyBtn.textContent = originalText;
                copyBtn.style.background = "";
                copyBtn.style.color = "";
            }, 2000);
        });
    });

    // Run on load
    updateUI();
});
