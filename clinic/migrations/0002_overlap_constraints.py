from django.db import migrations
# Defensa adicional frente a inserciones SQL fuera de los servicios de Django.
class Migration(migrations.Migration):
    dependencies=[('clinic','0001_initial')]
    operations=[migrations.RunSQL(
        sql="""
        CREATE EXTENSION IF NOT EXISTS btree_gist;
        ALTER TABLE clinic_appointment ADD CONSTRAINT appointment_vet_no_overlap
          EXCLUDE USING gist (vet_id WITH =, tstzrange(starts, ends, '[)') WITH &&)
          WHERE (status IN ('SCHEDULED','IN_PROGRESS'));
        ALTER TABLE clinic_appointment ADD CONSTRAINT appointment_pet_no_overlap
          EXCLUDE USING gist (pet_id WITH =, tstzrange(starts, ends, '[)') WITH &&)
          WHERE (status IN ('SCHEDULED','IN_PROGRESS'));
        ALTER TABLE clinic_shift ADD CONSTRAINT shift_vet_no_overlap
          EXCLUDE USING gist (vet_id WITH =, tstzrange(starts, ends, '[)') WITH &&);
        ALTER TABLE clinic_pet ADD CONSTRAINT pet_species_valid CHECK (species IN ('DOG','CAT'));
        ALTER TABLE clinic_payment ADD CONSTRAINT payment_positive CHECK (amount > 0 AND tendered >= amount AND change = tendered - amount);
        """,
        reverse_sql="""
        ALTER TABLE clinic_appointment DROP CONSTRAINT appointment_vet_no_overlap;
        ALTER TABLE clinic_appointment DROP CONSTRAINT appointment_pet_no_overlap;
        ALTER TABLE clinic_shift DROP CONSTRAINT shift_vet_no_overlap;
        ALTER TABLE clinic_pet DROP CONSTRAINT pet_species_valid;
        ALTER TABLE clinic_payment DROP CONSTRAINT payment_positive;
        """
    )]
