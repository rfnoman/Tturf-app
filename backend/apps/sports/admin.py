"""Catalogue administration.

Admins curate sports here, and review proposals with the two actions DOMAIN §2 calls
for: *approve* (creates the sport) and *merge into…*. Both go through
``apps/sports/services.py`` so the admin can never leave a proposal in a state the API
could not produce.
"""

from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .models import (
    Attribute,
    Sport,
    SportAttributeWeight,
    SportFormat,
    SportProposal,
    SportSkill,
    StatDefinition,
)
from .services import approve_sport_proposal, merge_sport_proposal, reject_sport_proposal


@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ("label", "key", "order")
    ordering = ("order",)
    search_fields = ("label", "key")
    prepopulated_fields = {"key": ("label",)}


class SportFormatInline(admin.TabularInline):
    model = SportFormat
    extra = 0
    prepopulated_fields = {"slug": ("name",)}


class SportSkillInline(admin.TabularInline):
    model = SportSkill
    extra = 0


class SportAttributeWeightInline(admin.TabularInline):
    model = SportAttributeWeight
    extra = 0
    autocomplete_fields = ("attribute",)


class StatDefinitionInline(admin.TabularInline):
    model = StatDefinition
    extra = 0


@admin.register(Sport)
class SportAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "met_value", "is_active", "order", "format_count")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    ordering = ("order", "name")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [
        SportFormatInline,
        SportSkillInline,
        SportAttributeWeightInline,
        StatDefinitionInline,
    ]

    @admin.display(description=_("formats"))
    def format_count(self, obj) -> int:
        return obj.formats.count()


@admin.register(SportFormat)
class SportFormatAdmin(admin.ModelAdmin):
    list_display = ("sport", "name", "players_per_side", "is_active")
    list_filter = ("sport", "is_active")
    search_fields = ("name", "sport__name")


@admin.register(SportSkill)
class SportSkillAdmin(admin.ModelAdmin):
    list_display = ("sport", "label", "key", "weight", "counts_toward_overall", "order")
    list_filter = ("sport", "counts_toward_overall")
    search_fields = ("label", "key", "sport__name")


@admin.register(StatDefinition)
class StatDefinitionAdmin(admin.ModelAdmin):
    list_display = ("sport", "label", "key", "value_type", "scope", "is_positive", "order")
    list_filter = ("sport", "value_type", "scope", "is_positive")
    search_fields = ("label", "key", "sport__name")


class MergeProposalForm(forms.Form):
    """Intermediate page for the "merge into…" action."""

    sport = forms.ModelChoiceField(
        queryset=Sport.objects.order_by("name"), label=_("Merge into sport")
    )
    note = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)


@admin.register(SportProposal)
class SportProposalAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "status",
        "proposed_by",
        "merged_into",
        "reviewed_by",
        "reviewed_at",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("name", "description", "proposed_by__email")
    readonly_fields = ("merged_into", "reviewed_by", "reviewed_at", "created_at", "updated_at")
    autocomplete_fields = ("proposed_by",)
    actions = ("approve_selected", "merge_selected", "reject_selected")

    @admin.action(description=_("Approve proposal (creates the sport)"))
    def approve_selected(self, request, queryset):
        created = 0
        for proposal in queryset:
            try:
                sport = approve_sport_proposal(proposal=proposal, reviewer=request.user)
            except ValidationError as exc:
                self.message_user(
                    request, f"{proposal.name}: {'; '.join(exc.messages)}", messages.ERROR
                )
                continue
            created += 1
            self.message_user(
                request,
                _(
                    "Created “%(sport)s”. It stays inactive until you add its formats, "
                    "skills and stat definitions."
                )
                % {"sport": sport.name},
                messages.SUCCESS,
            )
        if created:
            self.message_user(request, f"Approved {created} proposal(s).", messages.INFO)

    @admin.action(description=_("Merge into an existing sport…"))
    def merge_selected(self, request, queryset):
        if "apply" in request.POST:
            form = MergeProposalForm(request.POST)
            if form.is_valid():
                sport = form.cleaned_data["sport"]
                note = form.cleaned_data["note"]
                merged = 0
                for proposal in queryset:
                    try:
                        merge_sport_proposal(
                            proposal=proposal,
                            reviewer=request.user,
                            sport=sport,
                            note=note,
                        )
                    except ValidationError as exc:
                        self.message_user(
                            request,
                            f"{proposal.name}: {'; '.join(exc.messages)}",
                            messages.ERROR,
                        )
                        continue
                    merged += 1
                self.message_user(
                    request, f"Merged {merged} proposal(s) into {sport.name}.", messages.SUCCESS
                )
                return HttpResponseRedirect(reverse("admin:sports_sportproposal_changelist"))
        else:
            form = MergeProposalForm()

        return render(
            request,
            "admin/sports/merge_proposal.html",
            {
                "title": _("Merge sport proposals"),
                "proposals": queryset,
                "form": form,
                "action": "merge_selected",
                "opts": self.model._meta,
            },
        )

    @admin.action(description=_("Reject proposal (uses the review note)"))
    def reject_selected(self, request, queryset):
        for proposal in queryset:
            try:
                reject_sport_proposal(
                    proposal=proposal,
                    reviewer=request.user,
                    note=proposal.review_note or "Not a fit for the catalogue right now.",
                )
            except ValidationError as exc:
                self.message_user(
                    request, f"{proposal.name}: {'; '.join(exc.messages)}", messages.ERROR
                )
