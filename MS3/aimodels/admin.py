# MS3/aimodels/admin.py

from django.contrib import admin
from django import forms
from .models import AIModel, ProviderSchema
import json

# --- Admin for ProviderSchema ---
class ProviderSchemaForm(forms.ModelForm):
    credentials_schema = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 15, 'cols': 100}),
        help_text="Enter the JSON Schema for credentials."
    )
    model_blueprints = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 30, 'cols': 100}),
        help_text="Enter the JSON array of model blueprints."
    )

    class Meta:
        model = ProviderSchema
        fields = '__all__'

    def clean_json_field(self, field_name):
        # Helper to validate JSON content from a form field
        data = self.cleaned_data[field_name]
        try:
            # The loaded JSON is what will be saved to the database
            return json.loads(data)
        except json.JSONDecodeError as e:
            raise forms.ValidationError(f"Invalid JSON in {field_name}: {e}")

    def clean_credentials_schema(self):
        return self.clean_json_field('credentials_schema')

    def clean_model_blueprints(self):
        return self.clean_json_field('model_blueprints')

@admin.register(ProviderSchema)
class ProviderSchemaAdmin(admin.ModelAdmin):
    form = ProviderSchemaForm
    list_display = ('provider_id', 'display_name')
    search_fields = ('provider_id', 'display_name')

# --- Admin for AIModel ---
class AIModelForm(forms.ModelForm):
    configuration = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 25, 'cols': 100}),
        help_text="For new models, enter simple JSON. The system will build the full schema on save."
    )
    
    class Meta:
        model = AIModel
        fields = '__all__'

    # --- THE FIX IS HERE ---
    # We add the same helper method to this form class as well.
    def clean_json_field(self, field_name):
        data = self.cleaned_data[field_name]
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            raise forms.ValidationError(f"Invalid JSON in {field_name}: {e}")
    # --- END OF FIX ---

    def clean_configuration(self):
        # Now this call will work correctly.
        return self.clean_json_field('configuration')

@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    form = AIModelForm
    list_display = ('name', 'provider', 'is_system_model', 'owner_id', 'updated_at')
    list_filter = ('is_system_model', 'provider')
    search_fields = ('name', 'owner_id')
    readonly_fields = ('id', 'created_at', 'updated_at', 'capabilities')
    
    fieldsets = (
        ('Core Details', {'fields': ('name', 'provider', 'is_system_model', 'owner_id')}),
        ('Configuration', {
            'fields': ('configuration', 'capabilities'),
            'description': """
                <p><b>When creating a new model, use this simple format:</b></p>
                <pre>{
    "model_name": "gemini-1.5-flash",
    "credentials": {"api_key": "your_shared_api_key"},
    "parameters": {"temperature": 0.7}
}</pre>
                <p>The full, backward-compatible schema will be generated and saved automatically.</p>
            """
        }),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )