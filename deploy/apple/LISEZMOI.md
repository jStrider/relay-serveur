# Certificats racine Apple

Téléchargés le 2026-10-18 depuis https://www.apple.com/certificateauthority/ (format DER). Ils servent à vérifier la chaîne de signature des transactions App Store (`app-store-server-library`). Empreintes SHA-256 (8 premiers octets) : AppleRootCA-G3 `63:34:3A:BF:B8:9A:6A:03`, AppleRootCA-G2 `C2:B9:B0:42:DD:57:83:0E`, AppleIncRootCertificate `B0:B1:73:0E:CB:C7:FF:45`, AppleComputerRootCertificate `0D:83:B6:11:B6:48:A1:A7`. Vérifier avec `openssl x509 -inform der -in <fichier> -noout -fingerprint -sha256`.
