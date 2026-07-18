# authentication/templatetags/auth_extras.py
from django import template

register = template.Library()

@register.filter(name='has_group')
def has_group(user, group_name):
    """Vérifie si un utilisateur appartient à un groupe (ou s'il est admin)"""
    if user.is_superuser:
        return True
    return user.groups.filter(name=group_name).exists()

@register.filter(name='is_manager_or_above')
def is_manager_or_above(user):
    """Vérifie si l'utilisateur est au moins Manager ou Gérant (ou admin)"""
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=['Gérant', 'Manager']).exists()



@register.filter(name='Gérant')
def is_gerant(user):
    """Vérifie si l'utilisateur est au moins Manager ou Gérant (ou admin)"""
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=['Gérant']).exists()