class ForgeVideoPlayer {
    constructor(containerId, videoSrc, shotData) {
        this.container = document.getElementById(containerId);
        this.videoSrc = videoSrc;
        this.shotData = shotData;
        this.isAnalyzing = false;
        this.render();
        this.attachEvents();
    }
    
    render() {
        this.container.innerHTML = `
            <div class="video-wrapper">
                <video id="forge-video" src="${this.videoSrc}" controls></video>
                <canvas id="forge-canvas" style="display:none;"></canvas>
            </div>
            <div class="video-controls">
                <button id="analyze-frame-btn" class="btn-primary">
                    Hermes, check this frame
                </button>
                <span id="analysis-status" class="text-secondary"></span>
            </div>
            <div id="analysis-result" class="analysis-panel" style="display:none;">
            </div>
        `;
    }

    attachEvents() {
        const btn = this.container.querySelector("#analyze-frame-btn");
        btn.addEventListener('click', () => this.analyzeCurrentFrame());
    }

    async analyzeCurrentFrame() {
        if (this.isAnalyzing) return;
        this.isAnalyzing = true;
        
        const video = this.container.querySelector("#forge-video");
        const canvas = this.container.querySelector("#forge-canvas");
        const status = this.container.querySelector("#analysis-status");
        const resultPanel = this.container.querySelector("#analysis-result");
        
        status.textContent = "Capturing frame...";
        
        // Draw current frame to canvas
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0);
        
        // Convert to base64 JPEG (quality 0.9)
        const frameBase64 = canvas.toDataURL('image/jpeg', 0.9).split(',')[1];
        const mimeType = "image/jpeg";
        
        status.textContent = "Sending to Kimi VL...";
        
        try {
            const response = await fetch('/api/visual-audit', {
                method: 'POST',
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    frame_base64: frameBase64,
                    mime_type: mimeType,
                    shot_id: this.shotData.shot_id,
                    expected_description: this.shotData.description,
                    lore_excerpt: this.shotData.lore_excerpt,
                    session_id: window.appSessionId || "unknown"
                })
            });
            
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Server error (${response.status}): ${errorText}`);
            }

            const verdict = await response.json();
            this.displayResult(verdict);
            status.textContent = "Analysis complete.";
        } catch (err) {
            status.textContent = "Error: " + err.message;
            console.error(err);
        } finally {
            this.isAnalyzing = false;
        }
    }

    displayResult(verdict) {
        const panel = this.container.querySelector("#analysis-result");
        panel.style.display = 'block';
        
        const statusColor = verdict.is_consistent === true ? 'green'
                          : verdict.is_consistent === false ? 'red'
                          : 'amber';
        const statusText = verdict.is_consistent === true ? 'CONSISTENT'
                         : verdict.is_consistent === false ? 'MISMATCH'
                         : 'UNAVAILABLE';
        
        panel.innerHTML = `
            <div class="verdict-header" style="color: var(--${statusColor})">
                <span class="verdict-badge">${statusText}</span>
                <span class="confidence">Score: ${(verdict.confidence_score * 100).toFixed(0)}%</span>
            </div>
            ${verdict.mismatch_details ? `
                <div class="mismatch-details">
                    <strong>Details:</strong> ${verdict.mismatch_details}
                </div>
            ` : ''}
            ${verdict.suggested_fix ? `
                <div class="suggested-fix">
                    <strong>Suggested Fix:</strong> ${verdict.suggested_fix}
                </div>
            ` : ''}
            ${verdict.error_category === "rate_limited" || verdict.error_category === "no_api_key" ? `
                <div class="api-warning" style="color: var(--amber)">
                    ${verdict.mismatch_details}
                </div>
            ` : ''}
        `;
    }
}
