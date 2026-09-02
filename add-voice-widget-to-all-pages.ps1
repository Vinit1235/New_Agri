# Add Voice Assistant Widget to All HTML Pages
# Run this script to automatically integrate the voice widget

Write-Host "========================================" -ForegroundColor Green
Write-Host "  Voice Widget Integration Script" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

$frontendDir = "c:\Users\VINIT\Desktop\Smile_Clinc\New_Agri\frontend"
$scriptTag = @"

    <!-- Voice Assistant Widget -->
    <script src="js/voice-assistant-widget.js"></script>
"@

# List of HTML files to update
$htmlFiles = @(
    "index.html",
    "crop-health.html",
    "smart-watering.html",
    "smart-fertilizer.html",
    "ai-yield-prediction.html",
    "login.html",
    "signup.html",
    "privacy-policy.html",
    "terms-of-service.html"
)

$added = 0
$skipped = 0
$errors = 0

foreach ($file in $htmlFiles) {
    $filePath = Join-Path $frontendDir $file
    
    if (Test-Path $filePath) {
        try {
            $content = Get-Content $filePath -Raw -Encoding UTF8
            
            # Check if widget already added
            if ($content -match "voice-assistant-widget\.js") {
                Write-Host "[SKIP] $file (already integrated)" -ForegroundColor Yellow
                $skipped++
            }
            else {
                # Add script tag before </body>
                if ($content -match "</body>") {
                    $newContent = $content -replace "</body>", "$scriptTag`n</body>"
                    Set-Content $filePath $newContent -NoNewline -Encoding UTF8
                    Write-Host "[ADD]  $file" -ForegroundColor Green
                    $added++
                }
                else {
                    Write-Host "[WARN] $file (no </body> tag found)" -ForegroundColor Red
                    $errors++
                }
            }
        }
        catch {
            Write-Host "[ERROR] $file - $($_.Exception.Message)" -ForegroundColor Red
            $errors++
        }
    }
    else {
        Write-Host "[MISS] $file (file not found)" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Summary" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "Added:   $added files" -ForegroundColor Green
Write-Host "Skipped: $skipped files" -ForegroundColor Yellow
Write-Host "Errors:  $errors files" -ForegroundColor Red
Write-Host ""

if ($added -gt 0) {
    Write-Host "✅ Voice widget successfully integrated!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Make sure backend is running" -ForegroundColor White
    Write-Host "2. Open any HTML page in Chrome" -ForegroundColor White
    Write-Host "3. Look for the green microphone button" -ForegroundColor White
    Write-Host "4. Click and speak to test!" -ForegroundColor White
}
else {
    Write-Host "ℹ️  No files were modified" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done! Press Enter to continue..."
Read-Host
