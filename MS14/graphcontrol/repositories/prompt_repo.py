from ..models import PromptTemplate
from .base_repo import BaseRepository
from .errors import NotFoundError


class PromptTemplateRepository(BaseRepository):
    def create_template(self, rule_id, placeholder_map, template_text):
        return PromptTemplate.objects.create(
            rule_id=rule_id,
            placeholder_map=placeholder_map,
            template_text=template_text,
        )

    def update_template(self, rule_id, text):
        updated = PromptTemplate.objects.filter(rule_id=rule_id).update(template_text=text)
        if updated == 0:
            raise NotFoundError(f"Prompt Template for Rule {rule_id} not found.")

    def get_template(self, rule_id):
        try:
            return PromptTemplate.objects.get(rule_id=rule_id)
        except PromptTemplate.DoesNotExist:
            raise NotFoundError(f"Prompt Template for Rule {rule_id} not found.")
