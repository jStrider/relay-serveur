-include .env
export

TF := terraform -chdir=deploy/terraform
SSH := ssh -i ~/.ssh/hermes_ed25519 -o StrictHostKeyChecking=accept-new debian@$$($(TF) output -raw host)
PLAYBOOK := cd deploy/ansible && ansible-playbook
WHEEL = $(shell ls -t dist/relay_serveur-*.whl 2>/dev/null | head -1)  # évalué à l'usage, après la cible dist

.PHONY: test dist infra deploy restore ssh backup-now backup-status

test:
	uv run pytest -q

dist:
	rm -rf dist && uv build --wheel -q

infra:
	$(TF) init -input=false
	$(TF) apply -var "zone=$(RELAY_ZONE)" -var "cloud_project_id=$(OVH_CLOUD_PROJECT_ID)"

# Inventaire et variables Ansible depuis les sorties Terraform et .env.
deploy/ansible/inventory.ini deploy/ansible/vars.yml: deploy/terraform/terraform.tfstate .env
	@printf "[relay]\nvps ansible_host=%s ansible_user=debian ansible_ssh_private_key_file=~/.ssh/hermes_ed25519\n" "$$($(TF) output -raw host)" > deploy/ansible/inventory.ini
	@$(TF) output -json | python3 -c 'import json,sys,os; o=json.load(sys.stdin); e=os.environ; v={k: o[k]["value"] for k in ("restic_repository","s3_access_key_id","s3_secret_access_key","nom_public")}; v.update(zone=e["RELAY_ZONE"], restic_password=e["RESTIC_PASSWORD"], relay_gratuit=e.get("RELAY_GRATUIT","0")=="1", apns_cle_fichier=os.path.expanduser(e.get("APNS_CLE_FICHIER","")), apns_cle_id=e.get("APNS_CLE_ID",""), apns_equipe=e.get("APNS_EQUIPE",""), apns_bundle=e.get("APNS_BUNDLE",""), apple_app_id=e.get("APPLE_APP_ID","0")); print(json.dumps(v))' > deploy/ansible/vars.yml
	@chmod 600 deploy/ansible/vars.yml

deploy: dist deploy/ansible/inventory.ini deploy/ansible/vars.yml
	$(PLAYBOOK) site.yml -e "wheel=$(abspath $(WHEEL))"

restore: deploy/ansible/inventory.ini
	$(PLAYBOOK) restore.yml

ssh:
	$(SSH)

backup-now:
	$(SSH) sudo systemctl start relay-backup.service

backup-status:
	$(SSH) 'sudo bash -c "set -a; . /etc/relay-backup.env; restic snapshots"'
