#sed -i '/ConditionPathExists=!\/run\/ostree-booted/d' /usr/lib/systemd/system/packagekit.service
echo "Generating base file manifest..."
/usr/libexec/rakuos/generate-base-manifest