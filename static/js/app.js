/**
 * ============================================================
 * SecuPi – app.js
 * AI Surveillance & Security Alert Monitoring Dashboard
 * Real-time API Integration
 * ============================================================
 */

// Track dismissed alert state to avoid nagging the user
let alertDismissed = false;
let lastAlertId = null;

/**
 * Open the Detailed Event modal popup.
 * Displays details including the captured image snapshot.
 * @param {Object} rec - Record object
 */
function openDetailModal(rec) {
    const modal = document.getElementById("detail-modal");
    const img = document.getElementById("modal-img");
    const title = document.getElementById("modal-title");
    const infoGrid = document.getElementById("modal-info-grid");

    title.innerHTML = `🚨 Unknown Person Alert`;
    if (rec.detType === "Confirmed Match") {
        title.innerHTML = `✅ Confirmed Match Event`;
    } else if (rec.detType === "Possible Match") {
        title.innerHTML = `⚠ Possible Match Event`;
    }

    img.src = rec.imageUrl;

    const nameLabel = rec.detType === "Possible Match" ? "Suggested Name" : "Name";
    const nameVal = rec.type === "Unknown" ? "—" : rec.name;

    infoGrid.innerHTML = `
        <div class="detail-row" style="display:flex; justify-content:space-between; padding:0.6rem 0; border-bottom:1px solid var(--border);">
            <span class="detail-label" style="color:var(--text-muted); font-size:0.85rem;">Detection Type</span>
            <span class="detail-val" style="font-weight:600;">${rec.detType}</span>
        </div>
        <div class="detail-row" style="display:flex; justify-content:space-between; padding:0.6rem 0; border-bottom:1px solid var(--border);">
            <span class="detail-label" style="color:var(--text-muted); font-size:0.85rem;">Confidence Score</span>
            <span class="detail-val" style="font-weight:600;">${rec.confidence}%</span>
        </div>
        <div class="detail-row" style="display:flex; justify-content:space-between; padding:0.6rem 0; border-bottom:1px solid var(--border);">
            <span class="detail-label" style="color:var(--text-muted); font-size:0.85rem;">${nameLabel}</span>
            <span class="detail-val" style="font-weight:600; color:var(--accent);">${nameVal}</span>
        </div>
        <div class="detail-row" style="display:flex; justify-content:space-between; padding:0.6rem 0; border-bottom:1px solid var(--border);">
            <span class="detail-label" style="color:var(--text-muted); font-size:0.85rem;">Detection ID</span>
            <span class="detail-val" style="font-weight:600; font-family:monospace;">#${rec.id}</span>
        </div>
        <div class="detail-row" style="display:flex; justify-content:space-between; padding:0.6rem 0; border-bottom:1px solid var(--border);">
            <span class="detail-label" style="color:var(--text-muted); font-size:0.85rem;">Date</span>
            <span class="detail-val" style="font-weight:600;">${rec.date}</span>
        </div>
        <div class="detail-row" style="display:flex; justify-content:space-between; padding:0.6rem 0; border-bottom:1px solid var(--border);">
            <span class="detail-label" style="color:var(--text-muted); font-size:0.85rem;">Time</span>
            <span class="detail-val" style="font-weight:600;">${rec.time}</span>
        </div>
        <div class="detail-row" style="display:flex; justify-content:space-between; padding:0.6rem 0; border-bottom:1px solid var(--border);">
            <span class="detail-label" style="color:var(--text-muted); font-size:0.85rem;">Camera Name</span>
            <span class="detail-val" style="font-weight:600;">${rec.camera}</span>
        </div>
        <div class="detail-row" style="display:flex; justify-content:space-between; padding:0.6rem 0;">
            <span class="detail-label" style="color:var(--text-muted); font-size:0.85rem;">Status</span>
            <span class="detail-val status-text ${rec.type === "Unknown" ? "alert" : "verified"}" style="font-weight:700;">${rec.status}</span>
        </div>
    `;

    modal.classList.remove("hidden");
}

/**
 * Close the Detailed Event modal popup.
 */
function closeDetailModal() {
    document.getElementById("detail-modal").classList.add("hidden");
}

/**
 * Fetch updates from the Flask server and refresh the dashboard.
 */
function pollSensorData() {
    fetch('/sensor_data?t=' + Date.now(), { cache: 'no-store' })
        .then(response => {
            if (!response.ok) throw new Error("HTTP error " + response.status);
            return response.json();
        })
        .then(data => {
            // 1. UPDATE HEADER STATUS BADGE
            const badge = document.getElementById("status-badge");
            const badgeLabel = document.getElementById("badge-label");

            if (data.tamper_alert) {
                badge.className = "status-badge alert";
                badgeLabel.innerText = "🚨 TAMPER ALERT";
            } else if (data.motion) {
                badge.className = "status-badge alert";
                badgeLabel.innerText = "🚨 MOTION DETECTED";
            } else {
                badge.className = "status-badge";
                badgeLabel.innerText = data.ai_always_on ? "AI Scanning Active" : "Standby Monitoring";
            }

            // 2. UPDATE INLINE HARDWARE SENSOR PILLS
            // PIR Motion Pill
            const pirPill = document.getElementById("sensor-pir");
            const valMotion = document.getElementById("val-motion");
            if (data.motion) {
                valMotion.innerText = "DETECTED";
                valMotion.style.color = "var(--danger)";
                pirPill.style.borderColor = "rgba(239, 68, 68, 0.4)";
                pirPill.style.background = "rgba(239, 68, 68, 0.05)";
            } else {
                valMotion.innerText = "Clear";
                valMotion.style.color = "var(--success)";
                pirPill.style.borderColor = "var(--border)";
                pirPill.style.background = "var(--bg-alt)";
            }

            // Proximity Pill - safe guard: distance might not always be a number
            const distPill = document.getElementById("sensor-dist");
            const valDistance = document.getElementById("val-distance");
            const distNum = parseFloat(data.distance);
            valDistance.innerText = isNaN(distNum) ? "--" : distNum.toFixed(1);
            if (data.tamper_alert) {
                valDistance.style.color = "var(--danger)";
                distPill.style.borderColor = "rgba(239, 68, 68, 0.4)";
                distPill.style.background = "rgba(239, 68, 68, 0.05)";
            } else {
                valDistance.style.color = "var(--text)";
                distPill.style.borderColor = "var(--border)";
                distPill.style.background = "var(--bg-alt)";
            }

            // System Status Pill
            document.getElementById("val-status").innerText = data.status;

            // 3. LIVE AI SURVEILLANCE WEB STREAM (Always Active)
            const liveImg = document.getElementById("live-img");
            if (liveImg && !liveImg.src.includes('/video_feed')) {
                liveImg.src = '/video_feed';
            }

            // Update checked state of Always-On AI Switch (synchronize state)
            const aiToggle = document.getElementById("ai-toggle-input");
            if (aiToggle && !aiToggle.disabled) {
                aiToggle.checked = data.ai_always_on;
            }

            // 4. LIVE SECURITY ALERT PANEL
            const alertPanel = document.getElementById("live-alert-panel");
            const alertMsg = document.getElementById("live-alert-message");
            const alertTime = document.getElementById("live-alert-time");

            // Look up the latest detection event
            const latestDet = (data.detections && data.detections.length > 0) ? data.detections[0] : null;

            if (data.tamper_alert) {
                alertMsg.innerText = "Ultrasonic Proximity Breach! Camera Tampering Detected!";
                alertTime.innerText = `Range: ${data.distance} cm`;
                alertPanel.classList.remove("hidden");
                alertDismissed = false; // Override dismiss if new tamper triggers
            } else if (latestDet && latestDet.type === "Unknown" && !alertDismissed) {
                alertMsg.innerText = "Unknown Person Spotted at camera feed!";
                alertTime.innerText = `Time: ${latestDet.time} | ID: #${latestDet.id}`;
                alertPanel.classList.remove("hidden");
                
                // If a new alert is generated, enable overlay banner
                if (lastAlertId !== latestDet.id) {
                    lastAlertId = latestDet.id;
                    alertDismissed = false;
                }
            } else {
                // Clear warning panel when state is clear
                if (!data.tamper_alert && (!latestDet || latestDet.type !== "Unknown")) {
                    alertPanel.classList.add("hidden");
                    alertDismissed = false;
                }
            }

            // 5. RENDER LATEST CAPTURED DETECTION CARD
            const detTime    = document.getElementById("det-time");
            const detDate    = document.getElementById("det-date");
            const detStatus  = document.getElementById("det-status");
            const latestImg  = document.getElementById("latest-img");
            const latestEmpty = document.getElementById("latest-empty");

            if (latestDet && detTime && detDate && detStatus) {
                detTime.innerText   = latestDet.time   || "--";
                detDate.innerText   = latestDet.date   || "--";
                detStatus.innerText = `${latestDet.name && latestDet.name !== "—" ? latestDet.name : "Unknown"} (${latestDet.confidence}% Match)`;

                if (latestImg) {
                    latestImg.src = latestDet.imageUrl;
                    latestImg.onerror = () => { latestImg.onerror = null; latestImg.src = "/static/captures/sample.png"; };
                    latestImg.onload  = () => { latestImg.classList.remove("hidden"); if (latestEmpty) latestEmpty.classList.add("hidden"); };
                }
                const cardFrame = document.getElementById("latest-frame");
                if (cardFrame) { cardFrame.onclick = () => openDetailModal(latestDet); cardFrame.style.cursor = "pointer"; }
            } else if (detTime) {
                detTime.innerText  = "—";
                detDate.innerText  = "—";
                detStatus.innerText = "—";
                if (latestImg)   latestImg.classList.add("hidden");
                if (latestEmpty) latestEmpty.classList.remove("hidden");
            }
            
            // 5.5 RENDER SERVER SYSTEM LOGS
            const logsList = document.getElementById("server-logs-list");
            if (logsList) {
                const logs = data.logs || [];
                if (logs.length === 0) {
                    logsList.innerHTML = `<li style="color:#888;">[System] No events logged yet...</li>`;
                } else {
                    logsList.innerHTML = "";
                    logs.forEach(log => {
                        const li = document.createElement("li");
                        li.innerText = log;
                        if (log.includes("ALERT") || log.includes("Intruder") || log.includes("Tamper")) {
                            li.style.color = "#ff4444";
                        } else if (log.includes("Recognized") || log.includes("Match")) {
                            li.style.color = "#44ff44";
                        } else {
                            li.style.color = "#aaa";
                        }
                        logsList.appendChild(li);
                    });
                }
            } // end if(logsList)

            // 6. RENDER UNKNOWN ALERTS LIST
            const unknownContainer = document.getElementById("unknown-alerts-container");
            const unknownDetections = data.detections ? data.detections.filter(d => d.type === "Unknown") : [];

            if (unknownDetections.length === 0) {
                unknownContainer.innerHTML = `
                    <div style="grid-column:1/-1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:0.6rem; padding:2rem; background:rgba(34,197,94,0.08); border:1.5px dashed rgba(34,197,94,0.3); border-radius:var(--radius); color:#15803D;">
                        <i class="fa-solid fa-shield-halved" style="font-size:2rem;"></i>
                        <span style="font-weight:600;">No Active Intruder Warnings &bull; All Systems Normal</span>
                    </div>
                `;
            } else {
                unknownContainer.innerHTML = "";
                // Show all unknown warnings (not capped at 2)
                unknownDetections.forEach((alert, idx) => {
                    const card = document.createElement("div");
                    card.style.cssText = "background:var(--card); border:1.5px solid rgba(239,68,68,0.35); border-radius:var(--radius); box-shadow:var(--shadow); padding:1.5rem; display:flex; flex-direction:column; gap:1.2rem; cursor:pointer;";

                    const imgSrc = alert.imageUrl || "/static/captures/sample.png";
                    card.innerHTML = `
                        <div style="display:flex; align-items:center; gap:0.6rem; font-weight:700; color:var(--danger); border-bottom:1.5px solid var(--border); padding-bottom:0.75rem;">
                            <i class="fa-solid fa-triangle-exclamation"></i>
                            <span style="flex-grow:1;">🚨 INTRUDER WARNING</span>
                            <span style="font-size:0.65rem; background:rgba(239,68,68,0.15); padding:0.2rem 0.6rem; border-radius:10px; color:var(--danger);">HIGH PRIORITY</span>
                        </div>
                        <div style="display:grid; grid-template-columns:1fr 1.6fr; gap:1.2rem;">
                            <div style="aspect-ratio:4/3; border-radius:var(--radius-sm); overflow:hidden; border:1px solid var(--border); background:var(--bg-alt);">
                                <img src="${imgSrc}" alt="Intruder" style="width:100%; height:100%; object-fit:cover;"
                                     onerror="this.onerror=null; this.src='/static/captures/sample.png';">
                            </div>
                            <div style="display:flex; flex-direction:column; gap:0.5rem; font-size:0.82rem;">
                                <div style="display:flex; justify-content:space-between;"><span style="color:var(--text-muted);">Time:</span><strong>${alert.time}</strong></div>
                                <div style="display:flex; justify-content:space-between;"><span style="color:var(--text-muted);">Date:</span><strong>${alert.date}</strong></div>
                                <div style="display:flex; justify-content:space-between;"><span style="color:var(--text-muted);">Camera:</span><strong>${alert.camera}</strong></div>
                                <div style="display:flex; justify-content:space-between;"><span style="color:var(--text-muted);">Log ID:</span><strong style="font-family:monospace;">#${alert.id}</strong></div>
                                <div style="display:flex; justify-content:space-between;"><span style="color:var(--text-muted);">Confidence:</span><strong style="color:var(--danger);">${alert.confidence}%</strong></div>
                            </div>
                        </div>
                    `;
                    card.onclick = () => openDetailModal(alert);
                    unknownContainer.appendChild(card);
                });
            }

            // 7. RENDER ACTIVITY LOGS TABLE
            const tbody = document.getElementById("logs-table-body");
            const logsCount = document.getElementById("logs-count");

            if (!data.detections || data.detections.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="7" style="text-align:center; padding: 2.5rem; color: var(--text-light);">
                            <i class="fa-regular fa-folder-open" style="font-size: 1.8rem; margin-bottom: 0.5rem; display:block;"></i>
                            No activity detection records captured yet
                        </td>
                    </tr>
                `;
                logsCount.innerText = "0 logs";
            } else {
                logsCount.innerText = `${data.detections.length} logs`;
                tbody.innerHTML = "";

                data.detections.forEach(log => {
                    const tr = document.createElement("tr");
                    tr.style.cursor = "pointer";
                    tr.onclick = () => openDetailModal(log);

                    if (log.type === "Unknown") {
                        tr.className = "log-row-unknown";
                        tr.style.background = "rgba(239, 68, 68, 0.02)";
                    } else {
                        tr.className = "log-row-recognized";
                    }

                    const typeBadge = log.type === "Unknown"
                        ? `<span class="badge-type unknown" style="display:inline-flex; align-items:center; gap:0.3rem; padding:0.25rem 0.65rem; border-radius:12px; font-size:0.75rem; font-weight:600; background:rgba(239, 68, 68, 0.1); color:var(--danger); border:1px solid rgba(239, 68, 68, 0.2);"><i class="fa-solid fa-triangle-exclamation"></i> Unknown</span>`
                        : `<span class="badge-type recognized" style="display:inline-flex; align-items:center; gap:0.3rem; padding:0.25rem 0.65rem; border-radius:12px; font-size:0.75rem; font-weight:600; background:rgba(34, 197, 94, 0.1); color:#15803D; border:1px solid rgba(34, 197, 94, 0.2);"><i class="fa-solid fa-user-check"></i> ${log.detType}</span>`;

                    const nameDisplay = log.type === "Unknown"
                        ? `<span style="color: var(--text-light); font-style: italic;">—</span>`
                        : `<strong style="color: var(--text);">${log.name}</strong>`;

                    const statusBadge = log.type === "Unknown"
                        ? `<span class="badge-status alert" style="display:inline-flex; align-items:center; gap:0.3rem; padding:0.22rem 0.6; border-radius:20px; font-size:0.7rem; font-weight:700; background:rgba(239, 68, 68, 0.12); color:var(--danger);"><i class="fa-solid fa-bell"></i> ALERT</span>`
                        : `<span class="badge-status verified" style="display:inline-flex; align-items:center; gap:0.3rem; padding:0.22rem 0.6; border-radius:20px; font-size:0.7rem; font-weight:700; background:rgba(34, 197, 94, 0.12); color:#15803D;"><i class="fa-solid fa-circle-check"></i> ${log.status.toUpperCase()}</span>`;

                    tr.innerHTML = `
                        <td style="padding:0.75rem 1rem; border-bottom:1px solid var(--border);">
                            <div class="log-thumb" style="width:48px; aspect-ratio:4/3; border-radius:6px; overflow:hidden; border:1px solid var(--border); background:var(--bg-alt);">
                                <img src="${log.imageUrl}" alt="Event Capture" style="width:100%; height:100%; object-fit:cover;" onerror="this.src='/static/captures/sample.png'">
                            </div>
                        </td>
                        <td style="padding:0.75rem 1rem; border-bottom:1px solid var(--border); font-family:monospace; font-weight:600; color:var(--text-muted);">#${log.id}</td>
                        <td style="padding:0.75rem 1rem; border-bottom:1px solid var(--border);">${typeBadge}</td>
                        <td style="padding:0.75rem 1rem; border-bottom:1px solid var(--border);">${nameDisplay}</td>
                        <td style="padding:0.75rem 1rem; border-bottom:1px solid var(--border); color:var(--text-muted); font-size:0.85rem;">${log.date}</td>
                        <td style="padding:0.75rem 1rem; border-bottom:1px solid var(--border); font-weight:500;">${log.time}</td>
                        <td style="padding:0.75rem 1rem; border-bottom:1px solid var(--border);">${statusBadge}</td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        })
        .catch(err => {
            console.error("SecuPi dashboard polling fail:", err);
        });
}

/**
 * Bind DOM clicks on dashboard mount
 */
document.addEventListener("DOMContentLoaded", () => {
    // Initial fetch trigger
    pollSensorData();

    // 0.5-second dynamic background polling for true real-time sensor updates
    setInterval(pollSensorData, 500);
    // Dismiss Warning Panel trigger
    const btnDismissAlert = document.getElementById("btn-close-alert");
    if (btnDismissAlert) {
        btnDismissAlert.addEventListener("click", () => {
            document.getElementById("live-alert-panel").classList.add("hidden");
            alertDismissed = true;
        });
    }

    // Bind Always-On AI Switch Toggle click
    const aiToggle = document.getElementById("ai-toggle-input");
    if (aiToggle) {
        aiToggle.addEventListener("change", () => {
            aiToggle.disabled = true; // Lock switch state during round-trip network call
            fetch('/toggle_ai', { method: 'POST', cache: 'no-store' })
                .then(res => {
                    if (!res.ok) throw new Error("HTTP error " + res.status);
                    return res.json();
                })
                .then(data => {
                    aiToggle.checked = data.ai_always_on;
                })
                .catch(err => {
                    console.error("AI Switch Toggle fail:", err);
                })
                .finally(() => {
                    aiToggle.disabled = false;
                    pollSensorData(); // Refresh indicators immediately
                });
        });
    }

    // Bind Close modal actions
    document.getElementById("btn-close-modal").addEventListener("click", closeDetailModal);
    document.getElementById("modal-overlay").addEventListener("click", closeDetailModal);
});
