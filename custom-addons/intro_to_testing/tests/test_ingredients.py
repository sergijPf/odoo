from odoo.tests import TransactionCase

class IngredientTests(TransactionCase):
    def test_single_serving_calculation(self):
        ingredient = self.env.ref("intro_to_testing.demo_taco_ingredient_beef")
        self.assertEqual(ingredient.adjust_per_serving(servings=1), ingredient.amount)
        self.assertEqual(
            ingredient.adjust_per_serving(servings=2), ingredient.amount * 2
        )
    # def test_should_pass(self):
    #     self.assertTrue(True)
    #
    # def test_should_fail(self):
    #     self.assertTrue(False)